"""step 4 · 공고 페이지 수집. resolver 로 어댑터 선택 → job_postings 저장/재사용.

재사용 규칙: normalized_url 이 같고 parse_status='success' 이며 fetched_at 이
JD_REUSE_TTL_HOURS(기본 24h) 이내면 행을 그대로 쓴다. 그 외에는 재fetch 후
jd_requirements 를 DELETE → 재INSERT 한다 (step 5).

확정본 §3 job_postings / task-09
"""

import structlog

from app.core.config import get_settings
from app.db.models.posting import JobPosting
from app.features.analysis import queries
from app.features.analysis.pipeline.context import RunContext, StepFailed
from app.integrations.jd.base import FetchedPosting, JdFetchError, JdUnsupportedSite
from app.integrations.jd.resolver import resolve_adapter
from app.shared.clock import now
from app.shared.enums import JobErrorCode, ParseStatus, PostingParseErrorCode

logger = structlog.get_logger(__name__)


async def run(ctx: RunContext) -> None:
    """공고를 수집하거나 재사용해 job.job_posting_id 를 확정한다."""
    settings = get_settings()
    url = ctx.job.posting_url or ""
    normalized = ctx.job.normalized_posting_url or url

    reusable = await queries.find_reusable_posting(ctx.db, normalized, settings.jd_reuse_ttl_hours)
    if reusable is not None:
        ctx.job_posting_id = reusable.id
        ctx.job.job_posting_id = reusable.id
        await ctx.db.commit()
        logger.info("jd_fetch_reused", run_id=str(ctx.job.id), posting_id=str(reusable.id))
        return

    try:
        adapter = resolve_adapter(url)
        fetched = await adapter.fetch(url)
    except JdUnsupportedSite as exc:
        await _record_failure(ctx, normalized, PostingParseErrorCode.UNSUPPORTED_SITE)
        raise StepFailed(JobErrorCode.UNSUPPORTED_SITE) from exc
    except JdFetchError as exc:
        await _record_failure(ctx, normalized, PostingParseErrorCode.JD_FETCH_FAILED)
        raise StepFailed(JobErrorCode.JD_FETCH_FAILED) from exc

    posting = await _upsert_posting(ctx, fetched)
    ctx.job_posting_id = posting.id
    ctx.job.job_posting_id = posting.id
    await ctx.db.commit()
    logger.info("jd_fetch_done", run_id=str(ctx.job.id), posting_id=str(posting.id))


async def _upsert_posting(ctx: RunContext, fetched: FetchedPosting) -> JobPosting:
    posting = await queries.get_posting_by_url(ctx.db, fetched.normalized_url)
    if posting is None:
        posting = JobPosting(normalized_url=fetched.normalized_url)
        ctx.db.add(posting)
    posting.source_url = ctx.job.posting_url or fetched.normalized_url
    posting.site_adapter = fetched.site_adapter
    posting.external_id = fetched.external_id
    posting.position = fetched.position
    posting.company_name = fetched.company_name
    posting.content_form = fetched.content_form
    posting.raw_text = fetched.raw_text
    posting.raw_json = fetched.raw_json
    posting.source_image_urls = fetched.source_image_urls
    posting.skill_tags = fetched.skill_tags
    posting.parse_status = str(ParseStatus.SUCCESS)
    posting.parse_error_code = None
    posting.fetched_at = now()
    await ctx.db.flush()
    return posting


async def _record_failure(
    ctx: RunContext, normalized_url: str, error_code: PostingParseErrorCode
) -> None:
    """실패도 어댑터별 성공률 비교를 위해 행으로 남긴다."""
    posting = await queries.get_posting_by_url(ctx.db, normalized_url)
    if posting is None:
        posting = JobPosting(
            normalized_url=normalized_url,
            source_url=ctx.job.posting_url or normalized_url,
            site_adapter="unknown",
        )
        ctx.db.add(posting)
    posting.parse_status = str(ParseStatus.FAILED)
    posting.parse_error_code = str(error_code)
    posting.fetched_at = now()
    await ctx.db.commit()
