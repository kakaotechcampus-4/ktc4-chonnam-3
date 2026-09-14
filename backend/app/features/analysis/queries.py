"""분석 결과 읽기 쿼리. router 는 db.execute 를 직접 부르지 않는다.

docs/layer-rules.md 1절 / task-11
"""

import uuid
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import Select, and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.analysis import (
    AnalysisJob,
    AnalysisRepoCandidate,
    AnalysisRepoCandidatePage,
    RepoMatchScore,
)
from app.db.models.document import UserDocument
from app.db.models.github import RepoAnalysis, Repository
from app.db.models.posting import JdRequirement, JobPosting
from app.shared.clock import now
from app.shared.enums import FilterStatus, JobStatus, JobType, ParseStatus

ACTIVE_JOB_STATUSES = (JobStatus.QUEUED, JobStatus.RUNNING)


@dataclass(frozen=True)
class CandidateRow:
    """카드 1장을 만들기 위해 필요한 행 묶음. AI 산출물은 없을 수 있다."""

    candidate: AnalysisRepoCandidate
    repository: Repository
    match_score: RepoMatchScore | None
    analysis: RepoAnalysis | None


# ── analysis_jobs ────────────────────────────────────────────────────
async def get_run(db: AsyncSession, run_id: uuid.UUID, user_id: uuid.UUID) -> AnalysisJob | None:
    """소유자 확인까지 포함한다. 남의 run 은 404 로 보인다."""
    stmt = select(AnalysisJob).where(
        AnalysisJob.id == run_id,
        AnalysisJob.user_id == user_id,
        AnalysisJob.job_type == JobType.ANALYSIS_RUN,
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def get_run_by_id(db: AsyncSession, run_id: uuid.UUID) -> AnalysisJob | None:
    """worker 용 — 소유자 검사 없이 run 을 읽는다."""
    return await db.get(AnalysisJob, run_id)


async def find_active_run(db: AsyncSession, user_id: uuid.UUID) -> AnalysisJob | None:
    """queued/running 인 analysis_run (부분 유니크와 같은 조건)."""
    stmt = select(AnalysisJob).where(
        AnalysisJob.user_id == user_id,
        AnalysisJob.job_type == JobType.ANALYSIS_RUN,
        AnalysisJob.status.in_([str(s) for s in ACTIVE_JOB_STATUSES]),
    )
    return (await db.execute(stmt)).scalars().first()


# ── documents ────────────────────────────────────────────────────────
async def get_document(
    db: AsyncSession, document_id: uuid.UUID, user_id: uuid.UUID
) -> UserDocument | None:
    """POST /documents/preview 로 만든 본인 문서만 허용한다."""
    stmt = select(UserDocument).where(
        UserDocument.id == document_id, UserDocument.user_id == user_id
    )
    return (await db.execute(stmt)).scalar_one_or_none()


# ── job_postings ─────────────────────────────────────────────────────
async def find_reusable_posting(
    db: AsyncSession, normalized_url: str, ttl_hours: int
) -> JobPosting | None:
    """normalized_url 기준 재사용. fetched_at 이 TTL 이내인 success 행만."""
    threshold = now() - timedelta(hours=ttl_hours)
    stmt = select(JobPosting).where(
        JobPosting.normalized_url == normalized_url,
        JobPosting.parse_status == str(ParseStatus.SUCCESS),
        JobPosting.fetched_at.is_not(None),
        JobPosting.fetched_at >= threshold,
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def get_posting_by_url(db: AsyncSession, normalized_url: str) -> JobPosting | None:
    stmt = select(JobPosting).where(JobPosting.normalized_url == normalized_url)
    return (await db.execute(stmt)).scalar_one_or_none()


async def list_requirements(db: AsyncSession, posting_id: uuid.UUID) -> list[JdRequirement]:
    stmt = (
        select(JdRequirement)
        .where(JdRequirement.job_posting_id == posting_id)
        .order_by(JdRequirement.display_order)
    )
    return list((await db.execute(stmt)).scalars().all())


# ── repositories ─────────────────────────────────────────────────────
async def list_user_repositories(db: AsyncSession, user_id: uuid.UUID) -> list[Repository]:
    stmt = (
        select(Repository)
        .where(Repository.user_id == user_id)
        .order_by(Repository.repo_pushed_at.desc().nullslast())
    )
    return list((await db.execute(stmt)).scalars().all())


async def count_user_repositories(db: AsyncSession, user_id: uuid.UUID) -> int:
    stmt = select(Repository.id).where(Repository.user_id == user_id)
    return len((await db.execute(stmt)).scalars().all())


# ── candidates ───────────────────────────────────────────────────────
def _candidate_stmt(job_id: uuid.UUID) -> Select[tuple[AnalysisRepoCandidate, Repository]]:
    return (
        select(AnalysisRepoCandidate, Repository)
        .join(Repository, Repository.id == AnalysisRepoCandidate.repository_id)
        .where(
            AnalysisRepoCandidate.analysis_job_id == job_id,
            AnalysisRepoCandidate.filter_status == str(FilterStatus.ELIGIBLE),
        )
    )


async def list_candidate_rows(
    db: AsyncSession, job_id: uuid.UUID, *, batch_no: int | None = None
) -> list[CandidateRow]:
    """카드용 후보 목록. 기본 응답에는 eligible 만 노출한다."""
    stmt = _candidate_stmt(job_id)
    if batch_no is not None:
        stmt = stmt.where(AnalysisRepoCandidate.batch_no == batch_no)
    stmt = stmt.order_by(
        AnalysisRepoCandidate.batch_no.nullslast(),
        AnalysisRepoCandidate.batch_rank.nullslast(),
        AnalysisRepoCandidate.base_rank,
    )
    pairs = [(row[0], row[1]) for row in (await db.execute(stmt)).all()]
    if not pairs:
        return []

    repo_ids = [repo.id for _, repo in pairs]
    score_stmt = select(RepoMatchScore).where(
        RepoMatchScore.analysis_job_id == job_id,
        RepoMatchScore.repository_id.in_(repo_ids),
    )
    scores = {row.repository_id: row for row in (await db.execute(score_stmt)).scalars().all()}

    analysis_stmt = (
        select(RepoAnalysis)
        .where(
            RepoAnalysis.repository_id.in_(repo_ids),
            RepoAnalysis.analysis_level == "shallow",
        )
        .order_by(RepoAnalysis.created_at.desc())
    )
    analyses: dict[uuid.UUID, RepoAnalysis] = {}
    for row in (await db.execute(analysis_stmt)).scalars().all():
        analyses.setdefault(row.repository_id, row)

    return [
        CandidateRow(
            candidate=candidate,
            repository=repo,
            match_score=scores.get(repo.id),
            analysis=analyses.get(repo.id),
        )
        for candidate, repo in pairs
    ]


async def max_batch_no(db: AsyncSession, job_id: uuid.UUID) -> int:
    stmt = select(AnalysisRepoCandidate.batch_no).where(
        AnalysisRepoCandidate.analysis_job_id == job_id,
        AnalysisRepoCandidate.batch_no.is_not(None),
    )
    values = [value for value in (await db.execute(stmt)).scalars().all() if value is not None]
    return max(values) if values else 0


async def count_eligible_candidates(db: AsyncSession, job_id: uuid.UUID) -> int:
    stmt = select(AnalysisRepoCandidate.id).where(
        AnalysisRepoCandidate.analysis_job_id == job_id,
        AnalysisRepoCandidate.filter_status == str(FilterStatus.ELIGIBLE),
    )
    return len((await db.execute(stmt)).scalars().all())


async def count_portfolio_mentioned(db: AsyncSession, job_id: uuid.UUID) -> int:
    """포트폴리오에서 언급돼 후보로 잡힌 repo 수 (matchedRepoCount 원천)."""
    stmt = select(AnalysisRepoCandidate.id).where(
        and_(
            AnalysisRepoCandidate.analysis_job_id == job_id,
            AnalysisRepoCandidate.selection_reason == "portfolio_mentioned",
        )
    )
    return len((await db.execute(stmt)).scalars().all())


# ── candidate pages ──────────────────────────────────────────────────
async def get_candidate_page(
    db: AsyncSession, job_id: uuid.UUID, page_no: int
) -> AnalysisRepoCandidatePage | None:
    stmt = select(AnalysisRepoCandidatePage).where(
        AnalysisRepoCandidatePage.analysis_job_id == job_id,
        AnalysisRepoCandidatePage.page_no == page_no,
    )
    return (await db.execute(stmt)).scalar_one_or_none()
