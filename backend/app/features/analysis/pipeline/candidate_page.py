"""candidate_page_analyze · '더 보기' page 단위 후보 분석.

page N 의 후보를 base_rank 순서로 잘라 batch_no=N 으로 확정하고 L0-b 를 수집한다.
L1(AI) 분석은 repo_analyze step 과 같은 경계를 쓰며 AI 연결 전에는 건너뛴다.
page job 은 전체 analysis_jobs.status 를 다시 running 으로 되돌리지 않는다.

spec/backend/features/analysis-run.md 더 보기 / task-11
"""

import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models.analysis import AnalysisRepoCandidate, AnalysisRepoCandidatePage
from app.db.models.user import GithubAccount, User
from app.features.analysis import queries
from app.features.analysis.pipeline.context import RunContext, StepFailed
from app.features.analysis.pipeline.steps import repo_analyze, repo_detail
from app.shared.clock import now
from app.shared.enums import CandidatePageStatus, FilterStatus, JobErrorCode

logger = structlog.get_logger(__name__)


async def analyze_candidate_page(db: AsyncSession, run_id: uuid.UUID, page: int) -> None:
    """page 하나를 분석 완료 상태로 만든다."""
    job = await queries.get_run_by_id(db, run_id)
    if job is None:
        logger.warning("candidate_page_run_missing", run_id=str(run_id))
        return
    page_row = await queries.get_candidate_page(db, run_id, page)
    if page_row is None:
        page_row = AnalysisRepoCandidatePage(
            analysis_job_id=run_id, page_no=page, requested_at=now()
        )
        db.add(page_row)
    if page_row.status == CandidatePageStatus.SUCCEEDED:
        return
    page_row.status = str(CandidatePageStatus.RUNNING)
    await db.commit()

    user = await db.get(User, job.user_id)
    if user is None:  # pragma: no cover
        await _fail(db, page_row, str(JobErrorCode.TOKEN_INVALID))
        return
    account = (
        await db.execute(select(GithubAccount).where(GithubAccount.user_id == user.id))
    ).scalar_one_or_none()
    ctx = RunContext(db=db, job=job, user=user, github_account=account)

    repository_ids = await _assign_batch(db, run_id, page)
    if not repository_ids:
        page_row.status = str(CandidatePageStatus.SUCCEEDED)
        page_row.completed_at = now()
        await db.commit()
        return

    ctx.batch_repository_ids = repository_ids
    try:
        await repo_detail.collect_details(ctx, repository_ids)
        await repo_analyze.run(ctx)
    except StepFailed as exc:
        await _fail(db, page_row, str(exc.error_code))
        return
    except Exception as exc:  # noqa: BLE001
        logger.exception("candidate_page_failed", run_id=str(run_id), page=page)
        await _fail(
            db,
            page_row,
            str(JobErrorCode.LLM_FAILED)
            if isinstance(exc, NotImplementedError)
            else "internal_error",
        )
        return

    page_row.status = str(CandidatePageStatus.SUCCEEDED)
    page_row.completed_at = now()
    await db.commit()
    logger.info("candidate_page_done", run_id=str(run_id), page=page, repos=len(repository_ids))


async def _assign_batch(db: AsyncSession, run_id: uuid.UUID, page: int) -> list[uuid.UUID]:
    """base_rank 순서로 page 구간을 잘라 batch_no/batch_rank 를 확정한다."""
    settings = get_settings()
    size = settings.repo_candidate_limit
    stmt = (
        select(AnalysisRepoCandidate)
        .where(
            AnalysisRepoCandidate.analysis_job_id == run_id,
            AnalysisRepoCandidate.filter_status == str(FilterStatus.ELIGIBLE),
        )
        .order_by(AnalysisRepoCandidate.base_rank)
    )
    eligible = list((await db.execute(stmt)).scalars().all())
    assigned = {c.repository_id for c in eligible if c.batch_no is not None and c.batch_no < page}
    remaining = [c for c in eligible if c.repository_id not in assigned and c.batch_no is None]
    target = remaining[:size] if page > 1 else []
    for rank, candidate in enumerate(target, start=1):
        candidate.batch_no = page
        candidate.batch_rank = rank
    await db.commit()
    return [candidate.repository_id for candidate in target]


async def _fail(db: AsyncSession, page_row: AnalysisRepoCandidatePage, error_code: str) -> None:
    page_row.status = str(CandidatePageStatus.FAILED)
    page_row.error_code = error_code
    page_row.completed_at = now()
    await db.commit()
