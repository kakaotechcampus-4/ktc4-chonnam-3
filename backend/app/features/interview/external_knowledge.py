"""검증된 Director의 외부 자료 요청을 유한 예산의 서버 Tool로 실행한다."""

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID, uuid4

import httpx
from anyio import CancelScope
from devon_ai import contracts as c
from devon_ai.query_policy import SENSITIVE_QUERY
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.db.models import AnalysisJob, InterviewExternalSource, InterviewSession, JobPosting
from app.features.interview.supplemental_sources import load_supplemental_sources
from app.integrations.search.tavily import SearchBudget, SearchError, TavilyClient, WebSource

type LookupStatus = Literal["found", "not_found", "insufficient_analysis", "tool_error"]

# 초기 공식 출처 범위다. 이 목록 자체가 검색 내용의 정확성·적용 시점을 보증하지 않는다.
OFFICIAL_DOMAINS = {
    "finance": ("developers.kftc.or.kr", "openbanking.or.kr"),
    "game": ("partner.steamgames.com",),
    "travel": ("data.go.kr", "api.visitkorea.or.kr"),
    "shopping": ("apicenter.commerce.naver.com",),
    "medical": ("hl7.org",),
    "mobility": ("gtfs.org",),
    "etc": ("elice.io", "developer.mozilla.org", "docs.python.org"),
}
_PRIVATE = SENSITIVE_QUERY


@dataclass(frozen=True)
class ExternalKnowledgeResult:
    status: LookupStatus
    sources: tuple[c.SupplementalSource, ...]
    searched_scope: tuple[str, ...]
    limitations: tuple[str, ...] = ()
    error_code: str | None = None


@dataclass(frozen=True)
class _CachedQuery:
    source_ids: tuple[UUID, ...]
    validated_at: datetime
    limitations: tuple[str, ...] = ()


def _cache_key(query: str, domains: tuple[str, ...]) -> str:
    data = json.dumps({"query": query.strip(), "domains": domains}, sort_keys=True)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _query_cache(value: object) -> dict[str, _CachedQuery]:
    if value is None:
        return {}
    if type(value) is not dict:
        raise ValueError("External cache state is invalid")
    result = {}
    for key, entry in value.items():
        if (
            type(key) is not str
            or re.fullmatch(r"[0-9a-f]{64}", key) is None
            or type(entry) is not dict
            or not {"source_ids", "validated_at"}
            <= set(entry)
            <= {"source_ids", "validated_at", "limitations"}
            or type(entry["source_ids"]) is not list
            or not entry["source_ids"]
            or any(type(item) is not str for item in entry["source_ids"])
            or type(entry["validated_at"]) is not str
        ):
            raise ValueError("External cache state is invalid")
        notes = entry.get("limitations", [])
        if type(notes) is not list or any(
            type(note) is not str or not note.strip() for note in notes
        ):
            raise ValueError("External cache state is invalid")
        ids = tuple(UUID(item) for item in entry["source_ids"])
        timestamp = datetime.fromisoformat(entry["validated_at"])
        if len(ids) != len(set(ids)) or timestamp.tzinfo is None:
            raise ValueError("External cache state is invalid")
        result[key] = _CachedQuery(ids, timestamp, tuple(notes))
    return result


def _cache_state(cache: dict[str, _CachedQuery]) -> dict[str, object]:
    return {
        key: {
            "source_ids": [str(item) for item in entry.source_ids],
            "validated_at": entry.validated_at.isoformat(),
            "limitations": list(entry.limitations),
        }
        for key, entry in cache.items()
    }


def _trace(result: ExternalKnowledgeResult) -> dict[str, object]:
    return asdict(
        c.ExternalSearchStatus(
            status=result.status,
            source_ids=tuple(source.source_id for source in result.sources),
            searched_scope=result.searched_scope,
            limitations=result.limitations,
            error_code=result.error_code,
        )
    )


def _usage(value: object) -> dict[str, int]:
    if value is None:
        return {"calls": 0, "credits": 0}
    if not isinstance(value, dict) or any(
        type(value.get(key)) is not int or value[key] < 0 for key in ("calls", "credits")
    ):
        raise ValueError("External budget state is invalid")
    return {"calls": value["calls"], "credits": value["credits"]}


def _reservations(value: object) -> dict[str, dict[str, int]]:
    if value is None:
        return {}
    if not isinstance(value, dict) or any(type(key) is not str for key in value):
        raise ValueError("External reservation state is invalid")
    return {key: _usage(item) for key, item in value.items()}


async def retrieve_external_knowledge(
    sessions: async_sessionmaker[AsyncSession],
    *,
    user_id: UUID,
    interview_id: UUID,
    queries: tuple[c.ExternalQueryRequest, ...],
    settings: Settings | None,
    http_client: httpx.AsyncClient | None = None,
    client: TavilyClient | None = None,
) -> ExternalKnowledgeResult:
    """검색·원문 수집·저장만 수행한다. 사용자 답변의 참/거짓이나 점수를 확정하지 않는다."""
    reservation_id = str(uuid4())
    cached_ids: set[UUID] = set()
    pending: list[c.ExternalQueryRequest] = []
    cached_limitations: list[str] = []
    async with sessions.begin() as db:
        interview = await db.scalar(
            select(InterviewSession)
            .where(
                InterviewSession.id == interview_id,
                InterviewSession.user_id == user_id,
            )
            .with_for_update()
        )
        if interview is None or interview.status != "in_progress":
            return ExternalKnowledgeResult(
                "tool_error", (), (), ("interview_unavailable",), "interview_unavailable"
            )
        owned_interview = interview
        category = await db.scalar(
            select(JobPosting.domain_category)
            .join(
                AnalysisJob,
                AnalysisJob.job_posting_id == JobPosting.id,
            )
            .where(AnalysisJob.id == interview.analysis_job_id)
        )
        domains = OFFICIAL_DOMAINS.get(category or "etc", OFFICIAL_DOMAINS["etc"])
        state = dict(interview.context_state or {})

        def unavailable(reason: str) -> ExternalKnowledgeResult:
            result = ExternalKnowledgeResult("tool_error", (), domains, (reason,), reason)
            state["external_searches"] = [_trace(result)]
            owned_interview.context_state = state
            return result

        if settings is None:
            return unavailable("external_tool_not_configured")
        try:
            # 하나라도 위험하면 batch 전체를 거절한다. 캐시·provider·신규 저장도 같은 질의다.
            queries = tuple(
                c.ExternalQueryRequest(query.validate_for_execution(), query.purpose)
                for query in queries
            )
        except c.ContractError:
            return unavailable("unsafe_external_query")
        now = datetime.now(UTC)
        cutoff = now - timedelta(seconds=settings.external_sources_cache_seconds)
        try:
            cache = _query_cache(state.get("external_query_cache"))
        except (ValueError, TypeError):
            return unavailable("external_cache_state_invalid")
        for query in queries:
            alias = cache.get(_cache_key(query.query, domains))
            if alias is not None and cutoff <= alias.validated_at <= now:
                owned_ids = set(
                    await db.scalars(
                        select(InterviewExternalSource.id).where(
                            InterviewExternalSource.interview_session_id == interview_id,
                            InterviewExternalSource.user_id == user_id,
                            InterviewExternalSource.id.in_(alias.source_ids),
                            InterviewExternalSource.content_scope == "extracted_page",
                        )
                    )
                )
                if owned_ids == set(alias.source_ids):
                    cached_ids.update(owned_ids)
                    cached_limitations.extend(alias.limitations)
                    continue
            pending.append(query)
        try:
            usage = _usage(state.get("external_search_usage"))
            reservations = _reservations(state.get("external_search_reservations"))
        except ValueError:
            return unavailable("external_budget_state_invalid")
        available_calls = settings.external_max_calls_per_interview - int(usage.get("calls", 0))
        available_credits = settings.external_max_credits_per_interview - int(
            usage.get("credits", 0)
        )
        call_limit = min(settings.tavily_max_calls, max(0, available_calls)) if pending else 0
        credit_limit = min(settings.tavily_max_credits, max(0, available_credits)) if pending else 0
        if pending and (call_limit < 2 or credit_limit < 2):
            return unavailable("external_budget_exhausted")
        usage["calls"] = int(usage.get("calls", 0)) + call_limit
        usage["credits"] = int(usage.get("credits", 0)) + credit_limit
        state["external_search_usage"] = usage
        reservations[reservation_id] = {"calls": call_limit, "credits": credit_limit}
        state["external_search_reservations"] = reservations
        interview.context_state = state

    budget = SearchBudget(call_limit, credit_limit)
    collected: list[tuple[str, WebSource]] = []
    limitations: list[str] = list(cached_limitations)
    query_limitations: dict[str, tuple[str, ...]] = {}
    error_code = None
    try:
        for query in pending:
            search = await provider.search(
                query.query, domains=domains, budget=budget, max_results=3
            )
            limitations.extend(search.limitations)
            if not search.sources:
                continue
            extracted = await provider.extract(
                tuple(source.url for source in search.sources),
                domains=domains,
                budget=budget,
            )
            limitations.extend(extracted.limitations)
            limitations.extend(f"extraction:{failure.reason}" for failure in extracted.failures)
            if not extracted.sources:
                limitations.append("search_snippets_only")
            query_limitations[_cache_key(query.query, domains)] = (
                *search.limitations,
                *extracted.limitations,
                *(f"extraction:{failure.reason}" for failure in extracted.failures),
            )
            collected.extend((query.query, source) for source in extracted.sources)
    except SearchError as exc:
        error_code = exc.reason
        limitations.append(f"external_lookup:{exc.reason}")
    finally:
        # 중단·실패 시에도 보수적으로 예약한 실제 호출 비용을 보존한다.
        with CancelScope(shield=True):
            async with sessions.begin() as db:
                row = await db.scalar(
                    select(InterviewSession)
                    .where(
                        InterviewSession.id == interview_id,
                        InterviewSession.user_id == user_id,
                    )
                    .with_for_update()
                )
                if row is not None:
                    state = dict(row.context_state or {})
                    reservations = _reservations(state.get("external_search_reservations"))
                    reserved = reservations.pop(reservation_id, None)
                    if reserved is not None:
                        usage = _usage(state.get("external_search_usage"))
                        usage["calls"] -= reserved["calls"] - budget.calls_used
                        usage["credits"] -= reserved["credits"] - budget.credits_used
                        state["external_search_usage"] = usage
                        state["external_search_reservations"] = reservations
                        row.context_state = state

    async with sessions.begin() as db:
        interview = await db.scalar(
            select(InterviewSession)
            .where(
                InterviewSession.id == interview_id,
                InterviewSession.user_id == user_id,
            )
            .with_for_update()
        )
        if interview is None or interview.status != "in_progress":
            return ExternalKnowledgeResult(
                "tool_error", (), domains, ("stale_interview",), "stale_interview"
            )
        refreshed: dict[str, set[UUID]] = {}
        for query_text, source in collected:
            existing = await db.scalar(
                select(InterviewExternalSource).where(
                    InterviewExternalSource.interview_session_id == interview_id,
                    InterviewExternalSource.user_id == user_id,
                    InterviewExternalSource.url == source.url,
                    InterviewExternalSource.content_hash == source.content_hash,
                )
            )
            if existing is None:
                existing = InterviewExternalSource(
                    user_id=user_id,
                    interview_session_id=interview_id,
                    query_text=query_text,
                    url=source.url,
                    title=source.title,
                    content=source.content,
                    content_scope=source.content_scope,
                    content_hash=source.content_hash,
                    retrieved_at=datetime.fromisoformat(source.retrieved_at.replace("Z", "+00:00")),
                    published_at=source.published_at,
                    limitations=list(source.limitations),
                )
                db.add(existing)
                await db.flush()
            cached_ids.add(existing.id)
            refreshed.setdefault(_cache_key(query_text, domains), set()).add(existing.id)
        sources = tuple(
            source
            for source in await load_supplemental_sources(db, interview_id)
            if source.kind == "external_source" and UUID(source.source_id) in cached_ids
        )
        if cached_ids and not sources:
            limitations.append("context_source_budget")
        status: LookupStatus = (
            "found"
            if sources
            else (
                "tool_error"
                if error_code
                else "insufficient_analysis"
                if limitations
                else "not_found"
            )
        )
        result = ExternalKnowledgeResult(
            status, sources, domains, tuple(dict.fromkeys(limitations)), error_code
        )
        state = dict(interview.context_state or {})
        # 인용 원문의 query_text·retrieved_at은 보존하고 질의별 재검증 시점만 갱신한다.
        cache = _query_cache(state.get("external_query_cache"))
        for key, ids in refreshed.items():
            cache[key] = _CachedQuery(
                tuple(sorted(ids)), datetime.now(UTC), query_limitations.get(key, ())
            )
        state["external_query_cache"] = _cache_state(cache)
        state["external_searches"] = [_trace(result)]
        interview.context_state = state
    return result
