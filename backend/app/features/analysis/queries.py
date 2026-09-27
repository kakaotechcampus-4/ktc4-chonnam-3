"""후보·확정 L1·추천 결과의 읽기 쿼리. 트랜잭션 종료는 호출자가 맡는다."""

import uuid
from collections.abc import Sequence
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.models.analysis import AnalysisJob, AnalysisRepoCandidate, RepoMatchScore
from app.db.models.github import RepoAnalysis, Repository
from app.shared.enums import Reason


async def get_run(
    session: AsyncSession, run_id: uuid.UUID, *, lock: Literal["update", "share"] | None = None
) -> AnalysisJob:
    query = (
        select(AnalysisJob)
        .where(AnalysisJob.id == run_id, AnalysisJob.job_type == "analysis_run")
        .execution_options(populate_existing=True)
    )
    if lock:
        query = query.with_for_update(read=lock == "share")
    run = await session.scalar(query)
    if run is None:
        raise AppError(Reason.NOT_FOUND)
    return run


async def candidate_repositories(
    session: AsyncSession, run_id: uuid.UUID
) -> list[tuple[AnalysisRepoCandidate, Repository]]:
    rows = await session.execute(
        select(AnalysisRepoCandidate, Repository)
        .join(Repository, Repository.id == AnalysisRepoCandidate.repository_id)
        .where(AnalysisRepoCandidate.analysis_job_id == run_id)
        .order_by(AnalysisRepoCandidate.base_rank)
        .execution_options(populate_existing=True)
    )
    return [(candidate, repo) for candidate, repo in rows]


async def bound_analyses(
    session: AsyncSession, candidates: Sequence[AnalysisRepoCandidate]
) -> dict[uuid.UUID, RepoAnalysis]:
    ids = set()
    for candidate in candidates:
        snapshot = (candidate.ranking_signals or {}).get("analysis")
        raw_id = snapshot.get("analysis_id") if isinstance(snapshot, dict) else None
        if isinstance(raw_id, str):
            try:
                ids.add(uuid.UUID(raw_id))
            except ValueError:
                continue
    if not ids:
        return {}
    results = await session.scalars(
        select(RepoAnalysis)
        .where(RepoAnalysis.id.in_(ids))
        .execution_options(populate_existing=True)
    )
    return {row.id: row for row in results}


async def run_matches(session: AsyncSession, run_id: uuid.UUID) -> dict[uuid.UUID, RepoMatchScore]:
    rows = await session.scalars(
        select(RepoMatchScore)
        .where(RepoMatchScore.analysis_job_id == run_id)
        .execution_options(populate_existing=True)
    )
    return {row.repository_id: row for row in rows}
