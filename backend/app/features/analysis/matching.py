"""추천 결과 저장. 호출자는 같은 트랜잭션을 commit하거나 rollback해야 한다."""

import uuid

from sqlalchemy import exists, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.logging import get_logger
from app.db.models.analysis import AnalysisJob, AnalysisRepoCandidate, RepoMatchScore
from app.db.models.github import Repository
from app.db.models.metric import Event
from app.db.models.posting import JdRequirement, JobPosting
from app.features.analysis import queries
from app.features.analysis.analysis_results import resolve_bound_analysis
from app.features.analysis.pipeline.steps.match_score import match_technologies
from app.shared.enums import CandidateSource, Reason
from app.shared.events import record_event

logger = get_logger(__name__)


def candidate_source(candidate: AnalysisRepoCandidate) -> CandidateSource:
    signals = candidate.ranking_signals or {}
    if signals.get("portfolio_mentioned") is True:
        return (
            CandidateSource.BOTH
            if signals.get("rule_eligible") is True
            else CandidateSource.PORTFOLIO
        )
    return CandidateSource.RULE_FILTER


async def refresh_matches(session: AsyncSession, run_id: uuid.UUID) -> list[RepoMatchScore]:
    """모든 페이지를 base_rank 순서로 재계산한다. 외부 API·LLM 호출은 하지 않는다."""
    # run 행의 배타 잠금으로 갱신을 직렬화해 모든 페이지 합산 추천 상한을 지킨다.
    run = await queries.get_run(session, run_id, lock="update")
    posting = await session.get(JobPosting, run.job_posting_id) if run.job_posting_id else None
    if posting is None or posting.parse_status != "succeeded":
        raise AppError(Reason.NOT_READY)
    requirements = (
        await session.scalars(
            select(JdRequirement)
            .where(JdRequirement.job_posting_id == posting.id)
            .order_by(JdRequirement.display_order)
        )
    ).all()
    candidates = await queries.candidate_repositories(session, run_id)
    analyses = await queries.bound_analyses(session, [c for c, _ in candidates])
    recommended = 0
    for candidate, repo in candidates:
        analysis = resolve_bound_analysis(candidate, analyses)
        selectable = (
            repo.user_id == run.user_id
            and not repo.is_private
            and repo.is_accessible
            and candidate.filter_status == "eligible"
            and analysis is not None
        )
        result = match_technologies(
            posting.skill_tags, analysis.tech_stack if selectable and analysis else (), requirements
        )
        is_recommended = bool(result.technologies) and recommended < 5
        recommended += int(is_recommended)
        values = {
            "analysis_job_id": run.id,
            "repository_id": repo.id,
            "score": None,
            "matched_requirement_ids": list(result.requirement_ids),
            "recommend_reason": result.reason,
            "is_recommended": is_recommended,
            "candidate_source": candidate_source(candidate).value,
        }
        statement = insert(RepoMatchScore).values(**values)
        await session.execute(
            statement.on_conflict_do_update(
                constraint="uq_match_scores_job_repo",
                set_={**values, "updated_at": func.now()},
            )
        )
    stored = await queries.run_matches(session, run_id)
    rows = [stored[c.repository_id] for c, _ in candidates]
    await _record_recommended(session, run, candidates, rows)
    return rows


async def _record_recommended(
    session: AsyncSession,
    run: AnalysisJob,
    candidates: list[tuple[AnalysisRepoCandidate, Repository]],
    rows: list[RepoMatchScore],
) -> None:
    """run의 첫 추천 저장 시점만 기록한다. 후속 페이지는 이 snapshot을 바꾸지 않는다."""
    try:
        # run 잠금은 호출자가 유지한다. 중복 SELECT의 잠금·권한 오류도 업무와 격리한다.
        async with session.begin_nested():
            already = await session.scalar(
                select(
                    exists().where(
                        Event.event_name == "repo_recommended", Event.analysis_job_id == run.id
                    )
                )
            )
            if already:
                return
            await record_event(
                session,
                "repo_recommended",
                user_id=run.user_id,
                analysis_job_id=run.id,
                payload={
                    "candidateCount": sum(c.filter_status != "excluded" for c, _ in candidates),
                    "recommendedCount": sum(row.is_recommended for row in rows),
                },
            )
    except SQLAlchemyError:
        logger.warning("event_record_failed", event_name="repo_recommended", exc_info=True)
