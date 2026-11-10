"""Wanted 수집 결과를 재사용하거나 새 자료로 저장한다. run·큐 실행은 task-11 책임이다."""

import asyncio
import hashlib
import json
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.db.models.posting import JdRequirement, JobPosting
from app.features.analysis.image_jd import extend_image_drafts
from app.features.analysis.posting_queries import (
    get_current_successful_posting,
    get_posting_requirements,
    get_reusable_failed_posting,
    lock_posting_url,
)
from app.integrations.jd.base import (
    PostingContent,
    PostingFetchError,
    PostingInvalidResponseError,
    UnsupportedSiteError,
)
from app.integrations.jd.wanted import WantedAdapter, extract_job_id
from app.llm_tasks.jd_extract import (
    JdExtractionError,
    JdRequirementDraft,
    build_requirement_drafts,
    is_requirement_heading,
)


def normalize_posting_url(posting_url: str) -> str:
    """기존 Wanted 검증으로 얻은 ID만 사용하고 추적 query와 fragment는 제거한다."""
    # 정규화에서 사라져도 raw_url에는 남을 수 있으므로 DB·HTTP보다 먼저 거절한다.
    posting_id = None if "\x00" in posting_url else extract_job_id(posting_url)
    if posting_id is None:
        raise UnsupportedSiteError("지원하는 Wanted 공고 URL이 필요합니다.")
    return f"https://www.wanted.co.kr/wd/{posting_id}"


def _fresh(posting: JobPosting | None, now: datetime, ttl: timedelta) -> bool:
    # 전달된 TTL의 경계까지 재사용하며, 단순 캐시 조회로 유효 기간을 연장하지 않는다.
    if posting is not None:
        raw = posting.raw_payload or {}
        if _partial_image(raw):
            retry_at = _image_retry_until(raw)
            if retry_at is not None:
                return (
                    posting.fetched_at is not None
                    and posting.fetched_at >= now - ttl
                    and now < retry_at
                )
            # 기존 부분 결과에는 최초 짧은 재확인만 허용한다. 새 시도부터 영속 예산을 기록한다.
            ttl = min(ttl, timedelta(seconds=60))
    return (
        posting is not None and posting.fetched_at is not None and posting.fetched_at >= now - ttl
    )


async def _reusable_success(
    db: AsyncSession, posting: JobPosting | None, now: datetime, ttl: timedelta
) -> bool:
    if posting is None or not _fresh(posting, now, ttl):
        return False
    # 이전 추출기가 제목을 요구사항으로 저장한 자료는 원문을 다시 확인해 새 ID로 보존한다.
    # 판별 규칙은 신규 추출과 공유하며 기존 요구행·면접의 참조 ID는 수정하지 않는다.
    requirements = await get_posting_requirements(db, posting.id)
    return not any(is_requirement_heading(row.text) for row in requirements)


def _content(snapshot: dict[str, object]) -> dict[str, object]:
    # 원문 그룹·표시 순서를 그대로 비교한다. 실제 수집 URL 표기만 내용 비교에서 제외한다.
    content = {
        key: value
        for key, value in snapshot.items()
        if key
        not in {
            "fetch_url",
            "_domain_classification",
            "_domain_classification_last_attempt",
            "_domain_classification_last_success",
            "_image_extraction",
            "_image_retry",
        }
    }
    metadata = content.get("source_metadata")
    if isinstance(metadata, dict):
        content["source_metadata"] = {
            key: value
            for key, value in metadata.items()
            if key not in {"image_processing", "image_extraction"}
        }
    return content


def _image_health(snapshot: dict[str, object]) -> dict[str, object] | None:
    extraction = snapshot.get("_image_extraction")
    metadata = snapshot.get("source_metadata")
    processing = metadata.get("image_processing") if isinstance(metadata, dict) else None
    if not isinstance(extraction, dict) and not isinstance(processing, dict):
        return None
    # 시도 시간·job ID가 달라진 것만으로 새 버전을 만들지는 않는다.
    return {
        "extraction": {
            key: extraction.get(key) if isinstance(extraction, dict) else None
            for key in ("status", "limitations", "rejected", "failure")
        },
        "collection_status": processing.get("status") if isinstance(processing, dict) else None,
    }


def _snapshot_content(content: PostingContent) -> dict[str, object]:
    snapshot = asdict(content)
    extraction = content.source_metadata.get("image_extraction")
    if extraction is not None:
        snapshot["_image_extraction"] = extraction
    return snapshot


def _partial_image(snapshot: dict[str, object]) -> bool:
    health = _image_health(snapshot)
    if health is None:
        return False
    extraction = health["extraction"]
    return health["collection_status"] in ("failed", "partial") or (
        isinstance(extraction, dict) and extraction.get("status") in ("failed", "partial")
    )


def _retry_time(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _image_retry_until(snapshot: dict[str, object]) -> datetime | None:
    state = snapshot.get("_image_retry")
    if not isinstance(state, dict):
        return None
    start, end = _retry_time(state.get("cycle_started_at")), _retry_time(state.get("next_retry_at"))
    attempts = state.get("attempts")
    if (
        type(attempts) is not int
        or not 1 <= attempts <= 3
        or start is None
        or end is None
        or not start <= end <= start + timedelta(hours=1)
    ):
        return None
    lease = _retry_time(state.get("lease_expires_at")) if state.get("owner") else None
    return max(end, lease) if lease is not None else end


def _next_image_retry(
    snapshot: dict[str, object], previous: dict[str, object] | None, now: datetime
) -> dict[str, object] | None:
    """같은 원문은 한 시간에 세 번까지 재확인한다. 조회만으로 예산을 연장하지 않는다."""
    if not _partial_image(snapshot):
        return None
    start, attempts = now, 1
    # OCR 전사·실패 사유가 달라진 것은 새 공고 원문이 아니다. 재시도 예산을 초기화하지 않는다.
    current_source = {
        key: value
        for key, value in _content(snapshot).items()
        if key not in {"source_blocks", "source_limitations"}
    }
    previous_source = {
        key: value
        for key, value in _content(previous or {}).items()
        if key not in {"source_blocks", "source_limitations"}
    }
    if previous is not None and previous_source == current_source:
        state = previous.get("_image_retry")
        if isinstance(state, dict) and _image_retry_until(previous) is not None:
            previous_start = _retry_time(state.get("cycle_started_at"))
            if previous_start is not None and previous_start <= now < previous_start + timedelta(
                hours=1
            ):
                start, attempts = previous_start, min(3, int(state["attempts"]) + 1)
    retry_at = (
        start + timedelta(hours=1) if attempts == 3 else now + timedelta(seconds=60 * attempts)
    )
    return {
        "attempts": attempts,
        "cycle_started_at": start.isoformat(),
        "next_retry_at": retry_at.isoformat(),
    }


def _validate_content(content: PostingContent) -> None:
    # JSONB뿐 아니라 TEXT·배열·요구사항에도 같은 원문이 저장되므로 모든 문자열을 검사한다.
    def validate(value: object) -> None:
        if isinstance(value, str):
            if "\x00" in value:
                raise ValueError
            value.encode("utf-8")
        elif isinstance(value, dict):
            for key, item in value.items():
                validate(key)
                validate(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                validate(item)

    try:
        data = asdict(content)
        validate(data)
        json.dumps(data, allow_nan=False)
    except (ValueError, UnicodeError, RecursionError):
        raise PostingInvalidResponseError("공고 원문에 저장할 수 없는 값이 있음") from None


def _posting(
    posting_url: str,
    normalized_url: str,
    content: PostingContent | None,
    fetched_at: datetime,
    *,
    error_code: str | None = None,
) -> JobPosting:
    return JobPosting(
        source="wanted",
        source_posting_id=normalized_url.rsplit("/", 1)[1],
        normalized_url=normalized_url,
        raw_url=posting_url,
        position=content.position if content else None,
        company_name=content.company_name if content else None,
        # industry 원문은 snapshot에 보존한다. 별도 도메인 분류 결과를 여기서 추측하지 않는다.
        domain_category=None,
        skill_tags=list(content.skill_tags) if content else [],
        # 전체 HTTP JSON이 아니라 어댑터가 확보한 원문 그룹과 출처의 스냅샷이다.
        raw_payload=_snapshot_content(content) if content else None,
        parse_status="failed" if error_code else "succeeded",
        parse_error_code=error_code,
        fetched_at=fetched_at if content else None,
    )


async def _same_requirements(
    db: AsyncSession, posting: JobPosting, drafts: list[JdRequirementDraft]
) -> bool:
    existing = await get_posting_requirements(db, posting.id)
    return [(r.category, r.text, r.display_order, r.tech_tags) for r in existing] == [
        (r.category, r.text, r.display_order, r.tech_tags) for r in drafts
    ]


@dataclass(frozen=True)
class PreparedPosting:
    """jd_fetch가 확보한 캐시 또는 원문을 jd_extract에 넘긴다."""

    posting_url: str
    normalized_url: str
    checked_at: datetime
    reuse_ttl_days: int
    cached: JobPosting | None = None
    content: PostingContent | None = None
    image_reservation_id: UUID | None = None
    image_owner: str | None = None


def _image_source(snapshot: dict[str, object], *, legacy: bool = False) -> dict[str, object]:
    # 이미지 전사·실패 문구는 수집한 공고의 변경이 아니다. 새 예약은 처리 전 해시를 보존한다.
    excluded = {"source_blocks", "source_limitations"}
    if legacy:
        # 구형 결과에는 처리 전 태그가 없어 이미지가 보탠 태그를 원문 변경으로 단정하지 않는다.
        excluded.add("skill_tags")
    return {key: value for key, value in _content(snapshot).items() if key not in excluded}


def _image_source_hash(snapshot: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(
            _image_source(snapshot),
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        ).encode()
    ).hexdigest()


def _same_image_source(
    current: dict[str, object], incoming: dict[str, object], source_hash: str
) -> bool:
    state = current.get("_image_retry")
    known_hash = state.get("source_hash") if isinstance(state, dict) else None
    if known_hash is not None:
        return isinstance(known_hash, str) and known_hash == source_hash
    return _image_source(current, legacy=True) == _image_source(incoming, legacy=True)


def _image_attempt_seconds(settings: Settings | None) -> float:
    # 이미지 전체 수집과 두 모델 시도·최대 한 번의 대기, 정리 여유를 포함한다.
    # 프로세스 유실 시에도 예약은 최대 한 시간 뒤 회수하며 같은 기한을 실제 실행에도 적용한다.
    image_seconds, model_seconds = 360.0, 0.0
    if settings is not None:
        image_seconds = settings.jd_image_total_timeout_seconds
        try:
            model_seconds = settings.require_llm().call_limits("jd_extract_image").timeout_seconds
        except ValueError:
            pass
    return min(3600.0, image_seconds + 3 * model_seconds + 30)


async def _reserve_image_attempt(
    sessions: async_sessionmaker[AsyncSession], prepared: PreparedPosting, settings: Settings | None
) -> PreparedPosting:
    assert prepared.content is not None
    snapshot = _snapshot_content(prepared.content)
    source_hash = _image_source_hash(snapshot)
    now = prepared.checked_at
    async with sessions.begin() as db:
        await lock_posting_url(db, prepared.normalized_url)
        current = await get_current_successful_posting(db, prepared.normalized_url)
        matching = await db.scalar(
            select(JobPosting)
            .where(
                JobPosting.normalized_url == prepared.normalized_url,
                JobPosting.raw_payload["_image_retry"]["source_hash"].astext == source_hash,
            )
            .order_by(JobPosting.created_at.desc(), JobPosting.id.desc())
            .limit(1)
        )
        same_current = current is not None and _same_image_source(
            current.raw_payload or {}, snapshot, source_hash
        )
        if matching is None and same_current:
            matching = current
        if (
            current is not None
            and (not _partial_image(current.raw_payload or {}) or same_current)
            and await _reusable_success(db, current, now, timedelta(days=prepared.reuse_ttl_days))
        ):
            db.expunge(current)
            return replace(prepared, cached=current)
        previous = matching.raw_payload or {} if matching is not None else {}
        state = previous.get("_image_retry")
        until = _image_retry_until(previous)
        if isinstance(state, dict) and until is not None and now < until:
            if (
                current is not None
                and current.fetched_at is not None
                and current.fetched_at >= now - timedelta(days=prepared.reuse_ttl_days)
            ):
                db.expunge(current)
                return replace(prepared, cached=current)
            raise JdExtractionError(
                "jd_extraction_failed", "같은 공고의 이미지 분석이 진행 또는 대기 중"
            )
        # 같은 수집 원문의 이미 확정한 주기만 이어간다. 실제 HTTP 전에 횟수를 소비한다.
        basis = {**snapshot, "_image_extraction": {"status": "partial"}}
        prior = {**basis, **({"_image_retry": state} if isinstance(state, dict) else {})}
        reserved = _next_image_retry(basis, prior, now)
        assert reserved is not None
        owner = str(uuid4())
        reserved.update(
            source_hash=source_hash,
            owner=owner,
            lease_expires_at=(
                now + timedelta(seconds=_image_attempt_seconds(settings))
            ).isoformat(),
        )
        if matching is None:
            matching = _posting(
                prepared.posting_url,
                prepared.normalized_url,
                prepared.content,
                now,
                error_code="jd_extraction_in_progress",
            )
            db.add(matching)
        matching.raw_payload = {**(matching.raw_payload or snapshot), "_image_retry": reserved}
        await db.flush()
        return replace(prepared, image_reservation_id=matching.id, image_owner=owner)


def _owned_image_state(
    posting: JobPosting | None, prepared: PreparedPosting
) -> dict[str, object] | None:
    raw = posting.raw_payload if posting is not None else None
    state = raw.get("_image_retry") if isinstance(raw, dict) else None
    if not isinstance(state, dict) or state.get("owner") != prepared.image_owner:
        return None
    return {key: value for key, value in state.items() if key not in {"owner", "lease_expires_at"}}


async def _save_posting_failure(
    session_factory: async_sessionmaker[AsyncSession],
    prepared: PreparedPosting,
    error_code: str,
) -> None:
    async with session_factory.begin() as db:
        await lock_posting_url(db, prepared.normalized_url)
        if prepared.image_reservation_id is not None:
            owned = await db.get(JobPosting, prepared.image_reservation_id)
            state = _owned_image_state(owned, prepared)
            if owned is not None and state is not None:
                # 실패·취소도 물리 호출 예산을 되돌리지 않으며 다른 소유자의 예약은 건드리지 않는다.
                failed_source: dict[str, object] = {}
                if owned.parse_status == "failed" and prepared.content is not None:
                    try:
                        _validate_content(prepared.content)
                    except PostingInvalidResponseError:
                        # 방금 거절한 원문을 실패 정리에서 DB에 다시 넣지 않는다.
                        pass
                    else:
                        failed_source = _snapshot_content(prepared.content)
                owned.raw_payload = {
                    **(owned.raw_payload or {}),
                    **failed_source,
                    "_image_retry": {**state, "last_error": error_code},
                }
                if owned.parse_status == "failed":
                    owned.parse_error_code = error_code
            return
        current = await get_reusable_failed_posting(db, prepared.normalized_url)
        if current is not None and isinstance(
            (current.raw_payload or {}).get("_image_retry"), dict
        ):
            # 원티드 수집 실패가 이미 소비한 이미지 예산·진행 예약을 지워 재호출을 열면 안 된다.
            current = None
        if current is not None and current.updated_at > prepared.checked_at:
            # 늦게 끝난 이전 요청이 더 최근 시도의 실패 상태를 덮어쓰지 않는다.
            return
        failure = _posting(
            prepared.posting_url,
            prepared.normalized_url,
            prepared.content,
            prepared.checked_at,
            error_code=error_code,
        )
        # 같은 오류가 반복돼 ORM이 변경을 생략해도 마지막 시도 시각은 명시적으로 남긴다.
        failure.updated_at = prepared.checked_at
        if current is None:
            db.add(failure)
        else:
            # 성공·참조 자료는 보존한다. 원문 없는 수집 실패로 바뀌면 이전 원문도 비운다.
            for name in (
                "raw_url",
                "position",
                "company_name",
                "skill_tags",
                "raw_payload",
                "parse_error_code",
                "fetched_at",
                "updated_at",
            ):
                setattr(current, name, getattr(failure, name))


async def fetch_posting(
    session_factory: async_sessionmaker[AsyncSession],
    posting_url: str,
    *,
    client: httpx.AsyncClient | None = None,
    now: datetime | None = None,
    reuse_ttl_days: int = 7,
) -> PreparedPosting:
    """캐시를 확인하거나 원문만 수집한다. HTTP 중 DB transaction은 유지하지 않는다."""
    normalized_url = normalize_posting_url(posting_url)
    checked_at = now or datetime.now(UTC)
    ttl = timedelta(days=reuse_ttl_days)
    async with session_factory() as db:
        current = await get_current_successful_posting(db, normalized_url)
        if current is not None and await _reusable_success(db, current, checked_at, ttl):
            db.expunge(current)
            return PreparedPosting(
                posting_url, normalized_url, checked_at, reuse_ttl_days, cached=current
            )

    try:
        content = await WantedAdapter(client=client).fetch(normalized_url)
        # 실패 기록에는 오염된 content를 넘기지 않아 오류를 저장하다 다시 실패하지 않는다.
        _validate_content(content)
    except PostingFetchError as error:
        # 성공 자료를 failed로 덮어쓰지 않는다. 예기치 않은 코드/DB 오류는 여기서 숨기지 않는다.
        await _save_posting_failure(
            session_factory,
            PreparedPosting(posting_url, normalized_url, now or datetime.now(UTC), reuse_ttl_days),
            error.code,
        )
        raise
    return PreparedPosting(
        posting_url, normalized_url, now or datetime.now(UTC), reuse_ttl_days, content=content
    )


async def complete_posting(
    session_factory: async_sessionmaker[AsyncSession],
    prepared: PreparedPosting,
    *,
    settings: Settings | None = None,
    http_client: httpx.AsyncClient | None = None,
) -> JobPosting:
    """수집 원문을 추출·저장한다. 기존 ID 참조와 URL 잠금·재사용 정책을 유지한다."""
    if prepared.cached is not None:
        return prepared.cached
    content = prepared.content
    if content is None:
        raise ValueError("공고 원문 또는 캐시가 필요합니다.")
    if content.image_urls:
        prepared = await _reserve_image_attempt(session_factory, prepared, settings)
        if prepared.cached is not None:
            return prepared.cached
    try:
        drafts = (
            build_requirement_drafts(content)
            if content.is_structured or not content.image_urls
            else []
        )
        source_refs: list[list[dict[str, object]]] = [[] for _ in drafts]
        if content.image_urls:
            async with asyncio.timeout(_image_attempt_seconds(settings)):
                image = await extend_image_drafts(
                    session_factory, content, drafts, settings=settings, http_client=http_client
                )
            content, drafts, source_refs = image.content, image.drafts, image.source_refs
            prepared = replace(prepared, content=content)
            _validate_content(content)
        if not drafts:
            raise JdExtractionError("jd_extraction_failed", "검증한 요구사항이 없음")
    except JdExtractionError as error:
        await _save_posting_failure(session_factory, prepared, error.code)
        raise
    except BaseException as error:
        if prepared.image_reservation_id is not None:
            await asyncio.shield(
                _save_posting_failure(session_factory, prepared, "jd_extraction_failed")
            )
        if isinstance(error, TimeoutError):
            raise JdExtractionError(
                "jd_extraction_failed", "이미지 공고 분석 시간 예산 소진"
            ) from None
        raise
    normalized_url = prepared.normalized_url
    checked_at = prepared.checked_at
    ttl = timedelta(days=prepared.reuse_ttl_days)
    snapshot = _snapshot_content(content)
    async with session_factory.begin() as db:
        await lock_posting_url(db, normalized_url)
        current = await get_current_successful_posting(db, normalized_url)
        owned = (
            await db.get(JobPosting, prepared.image_reservation_id)
            if prepared.image_reservation_id
            else None
        )
        reserved = _owned_image_state(owned, prepared) if owned is not None else None
        if prepared.image_reservation_id is not None and reserved is None:
            # 만료 후 새 소유자가 재예약한 실행의 늦은 결과는 저장하지 않는다.
            if current is not None:
                db.expunge(current)
                return current
            raise JdExtractionError("jd_extraction_failed", "이미지 분석 예약이 변경됨")
        if owned is not None and reserved is not None:
            owned.raw_payload = {**(owned.raw_payload or {}), "_image_retry": reserved}
        image_retry = reserved if reserved is not None and _partial_image(snapshot) else None
        same_source = reserved is None
        if reserved is not None and current is not None:
            source_hash = reserved["source_hash"]
            assert isinstance(source_hash, str)
            same_source = _same_image_source(current.raw_payload or {}, snapshot, source_hash)
        newer_completed = (
            current is not None
            and owned is not None
            and current.created_at > owned.created_at
            and current.fetched_at is not None
            and current.fetched_at >= checked_at
        )
        if (
            current is not None
            and current.id != prepared.image_reservation_id
            and (
                same_source
                and await _reusable_success(db, current, checked_at, ttl)
                or newer_completed
            )
        ):
            # 같은 원문의 캐시만 재사용한다. 먼저 잡힌 옛 원문의 lease가 새 원문을 가리지
            # 않으며, 더 나중에 확인·완료한 새 버전은 늦게 끝난 옛 실행으로 덮지 않는다.
            result = current
        elif (
            current is not None
            and current.raw_payload is not None
            and _content(current.raw_payload) == _content(snapshot)
            and _image_health(current.raw_payload) == _image_health(snapshot)
            and await _same_requirements(db, current, drafts)
        ):
            # 내용·요구사항 ID·최초 생성 시각은 불변이며 실제 재확인 시각만 갱신한다.
            current.fetched_at = checked_at
            raw = {
                key: value
                for key, value in (current.raw_payload or {}).items()
                if key != "_image_retry"
            }
            current.raw_payload = {**raw, **({"_image_retry": image_retry} if image_retry else {})}
            result = current
        else:
            result = _posting(prepared.posting_url, normalized_url, content, checked_at)
            if image_retry is not None:
                result.raw_payload = {**(result.raw_payload or {}), "_image_retry": image_retry}
            db.add(result)
            await db.flush()
            db.add_all(
                JdRequirement(
                    job_posting_id=result.id, **asdict(draft), source_refs=source_refs[index]
                )
                for index, draft in enumerate(drafts)
            )
        await db.flush()
        await db.refresh(result)
        # expire_on_commit=True인 호출자도 반환된 자료를 안전하게 읽을 수 있게 한다.
        db.expunge(result)
    return result


async def get_or_fetch_posting(
    session_factory: async_sessionmaker[AsyncSession],
    posting_url: str,
    *,
    client: httpx.AsyncClient | None = None,
    now: datetime | None = None,
    reuse_ttl_days: int = 7,
    settings: Settings | None = None,
) -> JobPosting:
    """기존 호출자를 위해 수집과 추출을 순서대로 실행한다."""
    prepared = await fetch_posting(
        session_factory, posting_url, client=client, now=now, reuse_ttl_days=reuse_ttl_days
    )
    return await complete_posting(session_factory, prepared, settings=settings, http_client=client)
