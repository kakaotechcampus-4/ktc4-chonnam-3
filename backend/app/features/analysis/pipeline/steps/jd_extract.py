"""step 5 · 공고 분석 → jd_requirements.

Wanted 는 requirements / preferred_points / skill_tags 가 항목별로 이미 나뉘어 오므로
이 단계는 결정적 변환이다 (LLM 호출 없음, docs/task-09 'Wanted 구조화 필드에서 추출').
이미지 본문 사이트가 추가되면 그때 LLM 추출 경계가 필요하다 — Sprint 2.

error_code 를 단계별로 나눈다 — unsupported_site / jd_fetch_failed 는 수집 실패,
jd_extraction_failed 는 구조화 필드에서 요구사항을 하나도 얻지 못한 경우다.

확정본 §3 parse_error_code / task-09
"""

import structlog
from sqlalchemy import delete

from app.core.config import get_settings
from app.db.models.posting import JdRequirement, JobPosting
from app.features.analysis import queries
from app.features.analysis.pipeline.context import RunContext, StepFailed
from app.integrations.jd.base import FetchedPosting, JdUnsupportedSite
from app.integrations.jd.resolver import resolve_adapter
from app.shared.enums import JobErrorCode, PostingParseErrorCode

logger = structlog.get_logger(__name__)


async def run(ctx: RunContext) -> None:
    """job_postings.raw_json -> jd_requirements 재생성."""
    settings = get_settings()
    if ctx.job_posting_id is None:  # pragma: no cover - jd_fetch 가 먼저 실패한 경우
        raise StepFailed(JobErrorCode.JD_FETCH_FAILED)

    posting = await ctx.db.get(JobPosting, ctx.job_posting_id)
    if posting is None:  # pragma: no cover
        raise StepFailed(JobErrorCode.JD_FETCH_FAILED)

    existing = await _count_existing(ctx, posting)
    if existing:
        logger.info("jd_extract_reused", run_id=str(ctx.job.id), count=existing)
        return

    try:
        adapter = resolve_adapter(posting.source_url)
        items = adapter.extract_requirements(_as_fetched(posting))
    except JdUnsupportedSite as exc:
        raise StepFailed(JobErrorCode.UNSUPPORTED_SITE) from exc

    if not items:
        posting.parse_error_code = str(PostingParseErrorCode.JD_EXTRACTION_FAILED)
        await ctx.db.commit()
        raise StepFailed(JobErrorCode.JD_EXTRACTION_FAILED)

    await ctx.db.execute(delete(JdRequirement).where(JdRequirement.job_posting_id == posting.id))
    for order, item in enumerate(items[: settings.jd_requirement_limit]):
        ctx.db.add(
            JdRequirement(
                job_posting_id=posting.id,
                requirement_type=item.requirement_type,
                requirement_text=item.text,
                tech_tags=item.tech_tags,
                display_order=order,
            )
        )
    await ctx.db.commit()
    logger.info("jd_extract_done", run_id=str(ctx.job.id), count=len(items))


async def _count_existing(ctx: RunContext, posting: JobPosting) -> int:
    """재사용한 공고면 요구사항도 그대로 쓴다 (LLM·재추출 0회)."""
    return len(await queries.list_requirements(ctx.db, posting.id))


def _as_fetched(posting: JobPosting) -> FetchedPosting:
    """저장된 공고 행을 어댑터 입력 형태로 되돌린다."""
    return FetchedPosting(
        site_adapter=posting.site_adapter,
        fetch_url=posting.normalized_url,
        normalized_url=posting.normalized_url,
        external_id=posting.external_id,
        position=posting.position,
        company_name=posting.company_name,
        raw_text=posting.raw_text or "",
        raw_json=posting.raw_json,
        source_image_urls=list(posting.source_image_urls or []),
        skill_tags=list(posting.skill_tags or []),
        content_form=posting.content_form,
    )
