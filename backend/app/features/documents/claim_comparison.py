"""선택 문서와 고정 SHA 코드의 대조를 한 배치로 실행·저장·재사용한다."""

import asyncio
import hashlib
import json
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID, uuid4

import httpx
from devon_ai import contracts as c
from devon_ai.llm_tasks.claim_code import (
    MAX_CLAIMS,
    MAX_EVIDENCES,
    ClaimComparisonResult,
    ClaimForComparison,
    unverified,
    unverified_reason,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import LLMSettings, Settings
from app.db.models import (
    DocumentClaim,
    DocumentClaimComparison,
    Evidence,
    InterviewSession,
    LLMCallRecord,
    SessionRepository,
    UserDocument,
)
from app.features.documents.selection import selected_documents
from app.features.interview.prepare_lease import owns_preparation
from app.llm_tasks.conflict import compare_document_claims
from app.llm_tasks.prompt_loader import (
    PromptConfigurationError,
    PromptNotFoundError,
    load_active_prompt,
)

CODE_INPUT_BYTES = 65536


def _expires(state: dict[str, Any]) -> datetime | None:
    raw = state.get("document_claim_comparison_expires_at")
    try:
        value = datetime.fromisoformat(raw) if isinstance(raw, str) else None
    except ValueError:
        return None
    return value if value is not None and value.tzinfo is not None else None


def _hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


@dataclass(frozen=True)
class _Input:
    claims: tuple[ClaimForComparison, ...]
    evidences: tuple[c.Evidence, ...]
    code_sources: tuple[dict[str, Any], ...]
    limitations: tuple[str, ...]

    def fingerprint(self, prompt: c.PromptSpec | None) -> str:
        return _hash(
            {
                "claims": [asdict(item) for item in self.claims],
                "evidences": [asdict(item) for item in self.evidences],
                "limitations": self.limitations,
                "budget": {
                    "claims": MAX_CLAIMS,
                    "evidences": MAX_EVIDENCES,
                    "code_bytes": CODE_INPUT_BYTES,
                },
                "prompt": asdict(prompt) if prompt else None,
            }
        )


async def _owned(
    db: AsyncSession,
    interview_id: UUID,
    job_id: UUID,
) -> InterviewSession | None:
    row = await db.scalar(
        select(InterviewSession).where(InterviewSession.id == interview_id).with_for_update()
    )
    return row if row is not None and owns_preparation(row, job_id=job_id) else None


async def _input(db: AsyncSession, interview: InterviewSession) -> _Input:
    documents = await selected_documents(db, interview)
    if not documents:
        return _Input((), (), (), ())
    # 문서 추출의 전역 교체와 같은 잠금 순서를 사용하고 외부 호출 전 트랜잭션을 끝낸다.
    rows = await db.scalars(
        select(UserDocument)
        .where(UserDocument.id.in_([d.id for d in documents]))
        .order_by(UserDocument.id)
        .with_for_update()
    )
    documents = tuple(rows)
    claims: list[ClaimForComparison] = []
    for document in documents:
        snapshot = document.source_snapshot or {}
        text = snapshot.get("text")
        if type(text) is not str or hashlib.sha256(text.encode()).hexdigest() != snapshot.get(
            "text_hash"
        ):
            continue
        active = set(document.claims_active_ids or ())
        for claim in await db.scalars(
            select(DocumentClaim)
            .where(DocumentClaim.document_id == document.id)
            .order_by(DocumentClaim.created_at, DocumentClaim.id)
        ):
            if (
                str(claim.id) not in active
                or claim.source_version != snapshot["text_hash"]
                or not claim.source_text
                or claim.source_text not in text
            ):
                continue
            assert claim.source_version is not None
            claims.append(
                ClaimForComparison(
                    str(claim.id),
                    claim.claim_type or "unknown",
                    claim.claim_text,
                    claim.source_text,
                    claim.source_version,
                    json.dumps(
                        {**(claim.source_location or {}), "document_id": str(document.id)},
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                )
            )
    sources = await db.scalars(
        select(Evidence)
        .join(
            SessionRepository,
            (SessionRepository.interview_session_id == Evidence.interview_session_id)
            & (SessionRepository.repository_id == Evidence.repository_id)
            & (SessionRepository.snapshot_head_sha == Evidence.git_ref),
        )
        .where(Evidence.interview_session_id == interview.id, Evidence.source_type == "file")
        .order_by(Evidence.repository_id, Evidence.path, Evidence.start_line, Evidence.id)
    )
    evidences: list[c.Evidence] = []
    references: list[dict[str, Any]] = []
    remaining, omitted = CODE_INPUT_BYTES, 0
    for item in sources:
        size = len(item.snippet.encode())
        if (
            not item.path
            or not item.snippet.strip()
            or size > remaining
            or len(evidences) >= MAX_EVIDENCES
        ):
            omitted += 1
            continue
        evidences.append(
            c.Evidence(
                str(item.id),
                str(item.repository_id),
                item.git_ref,
                item.source_type,
                item.path,
                item.metadata_key,
                item.snippet,
                item.tool_name,
                item.summary,
                item.start_line,
                item.end_line,
            )
        )
        references.append(
            {
                "evidence_id": str(item.id),
                "repository_id": str(item.repository_id),
                "git_ref": item.git_ref,
                "path": item.path,
                "start_line": item.start_line,
                "end_line": item.end_line,
                "content_hash": hashlib.sha256(item.snippet.encode()).hexdigest(),
            }
        )
        remaining -= size
    limitations = ("provided_code_snippets_only",) + (
        (f"comparison_code_budget_excluded:{omitted}",) if omitted else ()
    )
    return _Input(tuple(claims), tuple(evidences), tuple(references), limitations)


def _state(
    row: InterviewSession,
    status: str,
    count: int,
    error: str | None = None,
    ids: tuple[str, ...] = (),
) -> None:
    row.context_state = {
        **(row.context_state or {}),
        "document_claim_comparison_status": status,
        "document_claim_comparison_count": count,
        "document_claim_comparison_error": error,
        "document_claim_comparison_active_ids": list(ids),
    }


async def prepare_selected_claim_comparisons(
    sessions: async_sessionmaker[AsyncSession],
    interview_id: UUID,
    settings: Settings,
    http_client: httpx.AsyncClient | None = None,
    *,
    job_id: UUID,
) -> None:
    """레포 원문 저장 뒤 호출한다. 한 논리 task만 실행하며 준비 임대를 다시 확인한다."""
    async with sessions.begin() as db:
        interview = await _owned(db, interview_id, job_id)
        if interview is None:
            return
        material = await _input(db, interview)
        if not material.claims:
            _state(interview, "succeeded", 0)
            return
        prompt: c.PromptSpec | None
        llm: LLMSettings | None
        needs_model = any(
            unverified_reason(item, has_code=bool(material.evidences)) is None
            for item in material.claims[:MAX_CLAIMS]
        )
        if needs_model:
            try:
                prompt = await load_active_prompt(db, "claim_code")
                llm = settings.require_llm()
            except (PromptNotFoundError, PromptConfigurationError, ValueError):
                prompt, llm = None, None
        else:
            prompt, llm = None, None
        fingerprint = material.fingerprint(prompt)
        cached = list(
            await db.scalars(
                select(DocumentClaimComparison)
                .where(
                    DocumentClaimComparison.interview_session_id == interview_id,
                    DocumentClaimComparison.input_fingerprint == fingerprint,
                    DocumentClaimComparison.execution_status.in_(("succeeded", "budget_exhausted")),
                )
                .order_by(DocumentClaimComparison.created_at.desc(), DocumentClaimComparison.id)
            )
        )
        batches: dict[UUID, list[DocumentClaimComparison]] = {}
        for item in cached:
            batches.setdefault(item.run_id, []).append(item)
        reusable = next(
            (batch for batch in batches.values() if len(batch) == len(material.claims)), None
        )
        if reusable is not None:
            overall = (
                "budget_exhausted"
                if any(row.execution_status == "budget_exhausted" for row in reusable)
                else "succeeded"
            )
            _state(interview, overall, len(reusable), ids=tuple(str(row.id) for row in reusable))
            return
        state = dict(interview.context_state or {})
        if (
            state.get("document_claim_comparison_status") == "running"
            and state.get("document_claim_comparison_job") == str(job_id)
            and state.get("document_claim_comparison_input") == fingerprint
            and (expires := _expires(state)) is not None
            and expires > datetime.now(UTC)
        ):
            return
        run_id = uuid4()
        _state(interview, "running", 0)
        interview.context_state = {
            **(interview.context_state or {}),
            "document_claim_comparison_run_id": str(run_id),
            "document_claim_comparison_job": str(job_id),
            "document_claim_comparison_input": fingerprint,
            "document_claim_comparison_started_at": datetime.now(UTC).isoformat(),
            "document_claim_comparison_expires_at": (
                datetime.now(UTC)
                + timedelta(
                    seconds=3 * llm.call_limits("claim_code").timeout_seconds if llm else 30
                )
            ).isoformat(),
        }

    attempts: list[c.AttemptMetadata] = []
    execution = "succeeded"
    selected = material.claims[:MAX_CLAIMS]
    cancelled = False
    if not needs_model:
        result = ClaimComparisonResult(
            tuple(
                unverified(
                    item,
                    unverified_reason(item, has_code=bool(material.evidences))
                    or "code_evidence_unavailable",
                )
                for item in selected
            ),
            None,
            (),
        )
    elif prompt is None or llm is None:
        execution = "not_available"
        result = ClaimComparisonResult(
            None,
            c.CallFailure(
                "provider", "claim_comparison_not_configured", "Comparison is not configured."
            ),
            (),
        )
    else:
        try:
            result = await compare_document_claims(
                selected,
                material.evidences,
                prompt=prompt,
                settings=llm,
                http_client=http_client,
                attempt_sink=attempts,
            )
        except asyncio.CancelledError:
            cancelled = True
            execution = "failed"
            result = ClaimComparisonResult(
                None,
                c.CallFailure("provider", "claim_comparison_cancelled", "Comparison cancelled."),
                tuple(attempts),
            )
    if result.failure and execution == "succeeded":
        execution = "failed"

    async def store() -> None:
        async with sessions.begin() as db:
            interview = await db.scalar(
                select(InterviewSession)
                .where(InterviewSession.id == interview_id)
                .with_for_update()
            )
            if interview is None:
                return
            record = LLMCallRecord(
                id=run_id,
                interview_session_id=interview_id,
                task_name="claim_code",
                attempts=[asdict(item) for item in result.attempts],
                failure=asdict(result.failure) if result.failure else None,
            )
            db.add(record)
            if not owns_preparation(interview, job_id=job_id) or (
                interview.context_state or {}
            ).get("document_claim_comparison_run_id") != str(run_id):
                record.discard_reason = "preparation_changed"
                return
            expires = _expires(interview.context_state or {})
            if expires is None or expires <= datetime.now(UTC):
                record.discard_reason = "comparison_lease_expired"
                _state(interview, "pending", 0, "comparison_lease_expired")
                return
            current = await _input(db, interview)
            if needs_model:
                try:
                    active = await load_active_prompt(db, "claim_code")
                except (PromptNotFoundError, PromptConfigurationError):
                    active = None
            else:
                active = None
            if cancelled or current.fingerprint(active) != fingerprint:
                record.discard_reason = "comparison_input_or_preparation_changed"
                _state(interview, "pending", 0, "comparison_input_changed")
                return
            by_id = {item.claim_id: item for item in result.data or ()}
            stored = []
            for index, claim in enumerate(material.claims):
                status = execution if index < MAX_CLAIMS else "budget_exhausted"
                error = (
                    result.failure.error_code
                    if result.failure
                    else "comparison_claim_budget_exceeded"
                )
                comparison = by_id.get(claim.claim_id) or unverified(claim, error)
                comparison = replace(
                    comparison,
                    limitations=tuple(
                        dict.fromkeys((*comparison.limitations, *material.limitations))
                    ),
                )
                existing = DocumentClaimComparison(
                    interview_session_id=interview_id,
                    claim_id=UUID(claim.claim_id),
                    run_id=run_id,
                    input_fingerprint=fingerprint,
                    document_version=claim.source_version,
                )
                db.add(existing)
                existing.claim_source = asdict(claim)
                existing.code_sources = list(material.code_sources)
                existing.status, existing.execution_status = comparison.status, status
                existing.result = asdict(comparison)
                existing.prompt_version = prompt.version if prompt else None
                existing.model = prompt.model if prompt else None
                stored.append(existing)
            await db.flush()
            overall = execution if len(material.claims) <= MAX_CLAIMS else "budget_exhausted"
            _state(
                interview,
                overall,
                len(material.claims),
                result.failure.error_code if result.failure else None,
                tuple(str(row.id) for row in stored),
            )

    if cancelled:
        await asyncio.shield(store())
        raise asyncio.CancelledError
    await store()


async def load_claim_comparison_sources(
    db: AsyncSession,
    interview: InterviewSession,
    *,
    include_historical: bool = False,
) -> tuple[c.SupplementalSource, ...]:
    """문서 주장과 대조 해석은 서로 다른 ID·버전으로 보존한다."""
    documents = {str(item.id): item for item in await selected_documents(db, interview)}
    if not documents or "document_claim_comparison_active_ids" not in (
        interview.context_state or {}
    ):
        return ()
    raw_ids = (interview.context_state or {}).get("document_claim_comparison_active_ids", [])
    if type(raw_ids) is not list or any(type(value) is not str for value in raw_ids):
        raise c.ContractError("schema", "comparison active ids")
    active_ids = set(cast(list[str], raw_ids))
    if not active_ids and not include_historical:
        return ()
    evidence_rows = await db.scalars(
        select(Evidence).where(Evidence.interview_session_id == interview.id)
    )
    sources = {str(item.id): item for item in evidence_rows}
    rows = await db.execute(
        select(DocumentClaimComparison, DocumentClaim)
        .join(DocumentClaim, DocumentClaim.id == DocumentClaimComparison.claim_id)
        .where(
            DocumentClaimComparison.interview_session_id == interview.id,
            DocumentClaim.document_id.in_([UUID(item) for item in documents]),
        )
        .order_by(DocumentClaimComparison.created_at, DocumentClaimComparison.id)
    )
    result = []
    for comparison, claim in rows:
        document = documents[str(claim.document_id)]
        current = (
            str(comparison.id) in active_ids
            and comparison.document_version == (document.source_snapshot or {}).get("text_hash")
            and str(claim.id) in (document.claims_active_ids or ())
        )
        if not include_historical and not current:
            continue
        limitations = tuple(comparison.result.get("limitations", []))
        invalid = False
        for reference in comparison.code_sources:
            source = sources.get(reference["evidence_id"])
            if (
                source is None
                or source.interview_session_id != interview.id
                or {
                    "git_ref": source.git_ref,
                    "path": source.path,
                    "content_hash": hashlib.sha256(source.snippet.encode()).hexdigest(),
                    "start_line": source.start_line,
                    "end_line": source.end_line,
                }
                != {
                    key: reference[key]
                    for key in ("git_ref", "path", "content_hash", "start_line", "end_line")
                }
            ):
                invalid = True
        content = {
            "claim_id": str(claim.id),
            "document_version": comparison.document_version,
            "execution_status": comparison.execution_status,
            "comparison": comparison.result
            if not invalid
            else {"status": "unverified", "reason": "comparison_code_source_unavailable"},
            "code_sources": comparison.code_sources,
        }
        result.append(
            c.SupplementalSource(
                source_id=str(comparison.id),
                kind="document_claim_comparison",
                content=json.dumps(content, ensure_ascii=False, sort_keys=True),
                location=f"document:{claim.document_id}:comparison:{comparison.id}",
                version=_hash({"input": comparison.input_fingerprint, "result": content}),
                limitations=limitations
                + ("model_interpretation_not_document_original",)
                + (("comparison_code_source_unavailable",) if invalid else ())
                + (("historical_document_claim_comparison",) if not current else ()),
                title=document.filename,
            )
        )
    return tuple(result)
