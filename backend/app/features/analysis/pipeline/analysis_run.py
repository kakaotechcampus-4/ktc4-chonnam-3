"""analysis_run · 7 step 오케스트레이션.

doc_extract → repo_select → repo_detail → jd_fetch → jd_extract → repo_analyze → match_score
각 step 전후로 Postgres steps/progress 를 갱신하고 Redis mirror·publish 를 잇는다.

종료 상태
- 모든 step 성공: succeeded
- 일부 repo 만 L0-b 실패: partial (FE 에는 failed 로 보이지만 result 는 조회 가능)
- hard blocker(StepFailed): failed + error_code

docs/pipeline.md 2절 / task-11
"""

import uuid
from collections.abc import Awaitable, Callable

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.analysis import AnalysisRepoCandidatePage
from app.db.models.user import GithubAccount, User
from app.features.analysis import queries
from app.features.analysis.pipeline.context import RunContext, StepFailed
from app.features.analysis.pipeline.steps import (
    doc_extract,
    jd_extract,
    jd_fetch,
    match_score,
    repo_analyze,
    repo_detail,
    repo_select,
)
from app.features.analysis.progress import finish_run, mark_step
from app.shared.clock import now
from app.shared.enums import (
    CandidatePageStatus,
    JobErrorCode,
    JobStatus,
    StepKey,
    StepStatus,
)

logger = structlog.get_logger(__name__)

#: 실행 순서. StepKey 순서와 같아야 한다.
STEPS: tuple[tuple[StepKey, Callable[[RunContext], Awaitable[None]]], ...] = (
    (StepKey.DOC_EXTRACT, doc_extract.run),
    (StepKey.REPO_SELECT, repo_select.run),
    (StepKey.REPO_DETAIL, repo_detail.run),
    (StepKey.JD_FETCH, jd_fetch.run),
    (StepKey.JD_EXTRACT, jd_extract.run),
    (StepKey.REPO_ANALYZE, repo_analyze.run),
    (StepKey.MATCH_SCORE, match_score.run),
)


async def run_analysis(db: AsyncSession, run_id: uuid.UUID) -> None:
    """ARQ task 가 부르는 진입점. 이미 끝난 run 은 다시 돌리지 않는다."""
    job = await queries.get_run_by_id(db, run_id)
    if job is None:
        logger.warning("analysis_run_missing", run_id=str(run_id))
        return
    if job.status not in (JobStatus.QUEUED, JobStatus.RUNNING):
        logger.info("analysis_run_already_finished", run_id=str(run_id), status=job.status)
        return

    user = await db.get(User, job.user_id)
    if user is None:  # pragma: no cover - FK 상 발생하지 않는다
        await finish_run(db, job, JobStatus.FAILED, error_code=str(JobErrorCode.TOKEN_INVALID))
        return

    account = (
        await db.execute(select(GithubAccount).where(GithubAccount.user_id == user.id))
    ).scalar_one_or_none()
    ctx = RunContext(db=db, job=job, user=user, github_account=account)

    job.started_at = job.started_at or now()
    for key, step in STEPS:
        await mark_step(db, job, key, StepStatus.RUNNING)
        try:
            await step(ctx)
        except StepFailed as exc:
            await mark_step(db, job, key, StepStatus.FAILED)
            await _fail_first_page(db, ctx, str(exc.error_code))
            await finish_run(db, job, JobStatus.FAILED, error_code=str(exc.error_code))
            logger.info("analysis_run_failed", run_id=str(run_id), step=str(key))
            return
        except Exception as exc:  # noqa: BLE001 - 어떤 예외도 run 을 매달아 두지 않는다
            logger.exception("analysis_run_step_error", run_id=str(run_id), step=str(key))
            await mark_step(db, job, key, StepStatus.FAILED)
            error_code = _error_code_for(exc)
            await _fail_first_page(db, ctx, error_code or "internal_error")
            await finish_run(db, job, JobStatus.FAILED, error_code=error_code)
            return
        await mark_step(db, job, key, StepStatus.SUCCEEDED)

    await _complete_first_page(db, ctx)
    if ctx.failed_repository_ids:
        first_error = next(iter(ctx.failed_repository_ids.values()))
        await finish_run(db, job, JobStatus.PARTIAL, error_code=first_error)
    else:
        await finish_run(db, job, JobStatus.SUCCEEDED)
    logger.info("analysis_run_done", run_id=str(run_id), status=job.status)


def _error_code_for(exc: Exception) -> str | None:
    """AI 경계 미구현은 llm_failed, 그 외 내부 오류는 코드 없이 남긴다.

    analysis_jobs.error_code 는 고정 목록이라 해당 없는 실패에 임의 값을 넣지 않는다.
    """
    return str(JobErrorCode.LLM_FAILED) if isinstance(exc, NotImplementedError) else None


async def _first_page(db: AsyncSession, ctx: RunContext) -> AnalysisRepoCandidatePage | None:
    return await queries.get_candidate_page(db, ctx.job.id, 1)


async def _complete_first_page(db: AsyncSession, ctx: RunContext) -> None:
    page = await _first_page(db, ctx)
    if page is None:
        return
    page.status = str(CandidatePageStatus.SUCCEEDED)
    page.completed_at = now()
    await db.commit()


async def _fail_first_page(db: AsyncSession, ctx: RunContext, error_code: str) -> None:
    page = await _first_page(db, ctx)
    if page is None:
        return
    page.status = str(CandidatePageStatus.FAILED)
    page.error_code = error_code
    page.completed_at = now()
    await db.commit()
