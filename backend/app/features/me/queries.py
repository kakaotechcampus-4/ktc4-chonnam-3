"""User-scoped reads for authenticated landing pages."""

from uuid import UUID

from sqlalchemy import ColumnElement, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.analysis import AnalysisJob
from app.db.models.github import Repository, UserProfileSummary
from app.db.models.interview import InterviewSession, SessionRepository
from app.db.models.posting import JobPosting
from app.db.models.report import InterviewReport
from app.db.models.user import GithubAccount

InterviewRow = tuple[InterviewSession, JobPosting | None, InterviewReport | None]


async def github_account(db: AsyncSession, user_id: UUID) -> GithubAccount | None:
    account: GithubAccount | None = await db.scalar(
        select(GithubAccount).where(GithubAccount.user_id == user_id)
    )
    return account


async def public_repository_count(db: AsyncSession, user_id: UUID) -> int:
    return int(
        await db.scalar(
            select(func.count())
            .select_from(Repository)
            .where(
                Repository.user_id == user_id,
                Repository.is_private.is_(False),
                Repository.is_accessible.is_(True),
            )
        )
        or 0
    )


async def latest_sync(db: AsyncSession, user_id: UUID) -> AnalysisJob | None:
    job: AnalysisJob | None = await db.scalar(
        select(AnalysisJob)
        .where(
            AnalysisJob.user_id == user_id,
            AnalysisJob.job_type == "initial_sync",
        )
        .order_by(AnalysisJob.created_at.desc(), AnalysisJob.id.desc())
        .limit(1)
    )
    return job


async def profile_summary(db: AsyncSession, user_id: UUID) -> UserProfileSummary | None:
    summary: UserProfileSummary | None = await db.scalar(
        select(UserProfileSummary).where(UserProfileSummary.user_id == user_id)
    )
    return summary


async def interview_stats(db: AsyncSession, user_id: UUID) -> tuple[int, float | None]:
    row = (
        await db.execute(
            select(func.count(InterviewSession.id), func.avg(InterviewReport.total_score))
            .outerjoin(InterviewReport, InterviewReport.interview_session_id == InterviewSession.id)
            .where(InterviewSession.user_id == user_id, InterviewSession.status == "completed")
        )
    ).one()
    return int(row[0]), float(row[1]) if row[1] is not None else None


def _history_filter(user_id: UUID) -> ColumnElement[bool]:
    """이력 목록 대상: 완료 면접과 첫 질문 뒤 중단된 면접(공통 0009)."""
    return and_(
        InterviewSession.user_id == user_id,
        or_(
            InterviewSession.status == "completed",
            and_(
                InterviewSession.status == "abandoned",
                InterviewSession.started_at.is_not(None),
            ),
        ),
    )


async def history_count(db: AsyncSession, user_id: UUID) -> int:
    """이력 목록의 전체 행 수. 페이지 계산용이며 평균 점수와 분모가 다르다."""
    count = await db.scalar(select(func.count(InterviewSession.id)).where(_history_filter(user_id)))
    return int(count or 0)


async def history_interviews(
    db: AsyncSession,
    user_id: UUID,
    *,
    limit: int,
    offset: int = 0,
) -> list[InterviewRow]:
    rows = await db.execute(
        select(InterviewSession, JobPosting, InterviewReport)
        .outerjoin(JobPosting, JobPosting.id == InterviewSession.job_posting_id)
        .outerjoin(InterviewReport, InterviewReport.interview_session_id == InterviewSession.id)
        .where(_history_filter(user_id))
        .order_by(
            func.coalesce(InterviewSession.completed_at, InterviewSession.started_at)
            .desc()
            .nulls_last(),
            InterviewSession.id.desc(),
        )
        .offset(offset)
        .limit(limit)
    )
    return [(interview, posting, report) for interview, posting, report in rows]


async def completed_interviews(
    db: AsyncSession,
    user_id: UUID,
    *,
    limit: int,
    offset: int = 0,
) -> list[InterviewRow]:
    rows = await db.execute(
        select(InterviewSession, JobPosting, InterviewReport)
        .outerjoin(JobPosting, JobPosting.id == InterviewSession.job_posting_id)
        .outerjoin(InterviewReport, InterviewReport.interview_session_id == InterviewSession.id)
        .where(InterviewSession.user_id == user_id, InterviewSession.status == "completed")
        .order_by(InterviewSession.completed_at.desc().nulls_last(), InterviewSession.id.desc())
        .offset(offset)
        .limit(limit)
    )
    return [(interview, posting, report) for interview, posting, report in rows]


async def repository_names(
    db: AsyncSession,
    user_id: UUID,
    interview_ids: list[UUID],
) -> dict[UUID, list[str]]:
    if not interview_ids:
        return {}
    rows = await db.execute(
        select(SessionRepository.interview_session_id, Repository.name)
        .join(Repository, Repository.id == SessionRepository.repository_id)
        .where(
            SessionRepository.interview_session_id.in_(interview_ids), Repository.user_id == user_id
        )
        .order_by(SessionRepository.display_order, Repository.name)
    )
    result: dict[UUID, list[str]] = {}
    for interview_id, name in rows:
        result.setdefault(interview_id, []).append(name)
    return result
