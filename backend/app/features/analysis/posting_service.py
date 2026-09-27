"""Wanted 수집 결과를 재사용하거나 새 자료로 저장한다. run·큐 실행은 task-11 책임이다."""

from dataclasses import asdict
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models.posting import JdRequirement, JobPosting
from app.features.analysis.posting_queries import (
    get_current_successful_posting,
    get_posting_requirements,
    lock_posting_url,
)
from app.integrations.jd.base import PostingContent, PostingFetchError, UnsupportedSiteError
from app.integrations.jd.wanted import WantedAdapter, extract_job_id
from app.llm_tasks.jd_extract import JdExtractionError, JdRequirementDraft, build_requirement_drafts


def normalize_posting_url(posting_url: str) -> str:
    """기존 Wanted 검증으로 얻은 ID만 사용하고 추적 query와 fragment는 제거한다."""
    posting_id = extract_job_id(posting_url)
    if posting_id is None:
        raise UnsupportedSiteError("지원하는 Wanted 공고 URL이 필요합니다.")
    return f"https://www.wanted.co.kr/wd/{posting_id}"


def _fresh(posting: JobPosting | None, now: datetime, ttl: timedelta) -> bool:
    # 정확히 7일인 경계까지 재사용하며, 단순 캐시 조회로 유효 기간을 연장하지 않는다.
    return (
        posting is not None and posting.fetched_at is not None and posting.fetched_at >= now - ttl
    )


def _content(snapshot: dict[str, object]) -> dict[str, object]:
    # 원문 그룹·표시 순서를 그대로 비교한다. 실제 수집 URL 표기만 내용 비교에서 제외한다.
    return {key: value for key, value in snapshot.items() if key != "fetch_url"}


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
        raw_payload=asdict(content) if content else None,
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


async def get_or_fetch_posting(
    session_factory: async_sessionmaker[AsyncSession],
    posting_url: str,
    *,
    client: httpx.AsyncClient | None = None,
    now: datetime | None = None,
    reuse_ttl_days: int = 7,
) -> JobPosting:
    """7일 이내 성공본은 그대로 반환하고, 변경 자료는 이전 참조를 유지하며 새 ID로 저장한다.

    반환 객체는 session에서 분리된 scalar 자료다. 요구사항은 posting_queries로 읽는다.
    HTTP 동안 DB session/transaction을 유지하지 않으며 외부 수집 실패만 실패 자료로 기록한다.
    """
    normalized_url = normalize_posting_url(posting_url)
    checked_at = now or datetime.now(UTC)
    ttl = timedelta(days=reuse_ttl_days)
    async with session_factory() as db:
        current = await get_current_successful_posting(db, normalized_url)
        if current is not None and _fresh(current, checked_at, ttl):
            db.expunge(current)
            return current

    content = None
    try:
        content = await WantedAdapter(client=client).fetch(normalized_url)
        drafts = build_requirement_drafts(content)
    except (PostingFetchError, JdExtractionError) as error:
        # 성공 자료를 failed로 덮어쓰지 않는다. 예기치 않은 코드/DB 오류는 여기서 숨기지 않는다.
        async with session_factory.begin() as db:
            await lock_posting_url(db, normalized_url)
            db.add(
                _posting(
                    posting_url,
                    normalized_url,
                    content,
                    now or datetime.now(UTC),
                    error_code=error.code,
                )
            )
        raise

    checked_at = now or datetime.now(UTC)
    snapshot = asdict(content)
    async with session_factory.begin() as db:
        await lock_posting_url(db, normalized_url)
        current = await get_current_successful_posting(db, normalized_url)
        if current is not None and _fresh(current, checked_at, ttl):
            # 수집 도중 다른 요청이 확정한 자료를 사용해 중복 INSERT와 늦은 덮어쓰기를 막는다.
            result = current
        elif (
            current is not None
            and current.raw_payload is not None
            and _content(current.raw_payload) == _content(snapshot)
            and await _same_requirements(db, current, drafts)
        ):
            # 내용·요구사항 ID·최초 생성 시각은 불변이며 실제 재확인 시각만 갱신한다.
            current.fetched_at = checked_at
            result = current
        else:
            result = _posting(posting_url, normalized_url, content, checked_at)
            db.add(result)
            await db.flush()
            db.add_all(JdRequirement(job_posting_id=result.id, **asdict(draft)) for draft in drafts)
        await db.flush()
        await db.refresh(result)
        # expire_on_commit=True인 호출자도 반환된 자료를 안전하게 읽을 수 있게 한다.
        db.expunge(result)
    return result
