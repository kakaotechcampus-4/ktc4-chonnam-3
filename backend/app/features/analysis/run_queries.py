"""분석 API의 소유권·페이지 배정 쿼리. commit은 service 책임이다."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.models.analysis import AnalysisJob, AnalysisRepoCandidate, AnalysisRepoCandidatePage
from app.shared.enums import Reason


async def owned_run(
    db: AsyncSession, run_id: UUID, user_id: UUID, ttl_seconds: int, *, lock: bool = False
) -> AnalysisJob:
    statement = (
        select(AnalysisJob)
        .where(
            AnalysisJob.id == run_id,
            AnalysisJob.user_id == user_id,
            AnalysisJob.job_type == "analysis_run",
        )
        .execution_options(populate_existing=True)
    )
    if lock:
        statement = statement.with_for_update()
    run = await db.scalar(statement)
    # 존재 여부를 다른 사용자에게 노출하지 않는다. 만료는 조회 제한이며 자료 삭제가 아니다.
    if run is None or run.created_at + timedelta(seconds=ttl_seconds) <= datetime.now(UTC):
        raise AppError(Reason.RUN_EXPIRED)
    return run


async def assigned_candidates(db: AsyncSession, run_id: UUID) -> list[AnalysisRepoCandidate]:
    return list(
        await db.scalars(
            select(AnalysisRepoCandidate)
            .where(
                AnalysisRepoCandidate.analysis_job_id == run_id,
                AnalysisRepoCandidate.batch_no.is_not(None),
            )
            .order_by(AnalysisRepoCandidate.base_rank)
        )
    )


async def allocate_page(db: AsyncSession, run_id: UUID, page: int, size: int) -> bool:
    """run 잠금을 가진 호출자가 전체 미배정 후보의 페이지 번호를 한 번 정한다."""
    remaining = list(
        await db.scalars(
            select(AnalysisRepoCandidate)
            .where(
                AnalysisRepoCandidate.analysis_job_id == run_id,
                AnalysisRepoCandidate.filter_status == "eligible",
                AnalysisRepoCandidate.batch_no.is_(None),
            )
            .order_by(AnalysisRepoCandidate.base_rank)
        )
    )
    for offset, candidate in enumerate(remaining):
        candidate.batch_no = 2 + offset // size
        candidate.batch_rank = 1 + offset % size
        candidate.selection_reason = "other"
    await db.flush()
    return (
        await db.scalar(
            select(AnalysisRepoCandidate.id)
            .where(
                AnalysisRepoCandidate.analysis_job_id == run_id,
                AnalysisRepoCandidate.batch_no == page,
            )
            .limit(1)
        )
        is not None
    )


async def candidate_page(
    db: AsyncSession, run_id: UUID, page: int
) -> AnalysisRepoCandidatePage | None:
    result: AnalysisRepoCandidatePage | None = await db.scalar(
        select(AnalysisRepoCandidatePage)
        .where(
            AnalysisRepoCandidatePage.analysis_job_id == run_id,
            AnalysisRepoCandidatePage.page_no == page,
        )
        .execution_options(populate_existing=True)
    )
    return result
