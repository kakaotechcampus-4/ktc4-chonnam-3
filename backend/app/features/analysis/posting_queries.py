"""공고 자료 조회. 저장 transaction과 commit은 posting_service가 소유한다."""

from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.analysis import AnalysisJob
from app.db.models.interview import InterviewSession
from app.db.models.posting import JdRequirement, JobPosting


async def get_current_successful_posting(
    db: AsyncSession, normalized_url: str
) -> JobPosting | None:
    """최근에 만든 성공 자료를 고른다. 실패 시도가 이전 성공 자료를 가리지 않는다."""
    # fetched_at은 동일 내용 재확인 때도 바뀌므로 버전 순서는 최초 생성 시각으로 정한다.
    posting: JobPosting | None = await db.scalar(
        select(JobPosting)
        .where(JobPosting.normalized_url == normalized_url, JobPosting.parse_status == "succeeded")
        .order_by(JobPosting.created_at.desc(), JobPosting.id.desc())
        .limit(1)
    )
    return posting


async def get_reusable_failed_posting(db: AsyncSession, normalized_url: str) -> JobPosting | None:
    """참조되지 않은 최신 실패 상태만 갱신 대상으로 고른다. URL 잠금 안에서 호출한다."""
    posting: JobPosting | None = await db.scalar(
        select(JobPosting)
        .where(
            JobPosting.normalized_url == normalized_url,
            JobPosting.parse_status == "failed",
            ~select(AnalysisJob.id).where(AnalysisJob.job_posting_id == JobPosting.id).exists(),
            ~select(InterviewSession.id)
            .where(InterviewSession.job_posting_id == JobPosting.id)
            .exists(),
        )
        .order_by(JobPosting.updated_at.desc(), JobPosting.created_at.desc(), JobPosting.id.desc())
        .limit(1)
    )
    return posting


async def get_posting_requirements(db: AsyncSession, posting_id: UUID) -> list[JdRequirement]:
    return list(
        await db.scalars(
            select(JdRequirement)
            .where(JdRequirement.job_posting_id == posting_id)
            .order_by(JdRequirement.display_order)
        )
    )


async def lock_posting_url(db: AsyncSession, normalized_url: str) -> None:
    """최초 행이 없는 URL도 직렬화한다. 외부 HTTP를 마친 뒤 짧은 저장 구간에서만 쓴다."""
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": f"wanted-posting:{normalized_url}"},
    )
