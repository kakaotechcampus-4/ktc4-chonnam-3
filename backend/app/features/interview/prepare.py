"""선택 run의 고정 자료를 준비하고 첫 검증된 Director 질문까지 확정한다."""

import asyncio
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

import httpx
from devon_ai import contracts as c
from sqlalchemy import JSON, and_, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.director.tools import EvidenceScope
from app.core.config import Settings
from app.db.models import (
    AnalysisJob,
    AnalysisRepoCandidate,
    DomainQuestionFrame,
    Evidence,
    InterviewSession,
    InterviewTurn,
    JobPosting,
    LLMCallRecord,
    RepoAnalysis,
    Repository,
    ScoreCriterion,
    SessionRepository,
    User,
)
from app.db.models.report import SCORE_KEYS
from app.features.analysis.analysis_results import resolve_bound_analysis
from app.features.interview.agent_context import AgentStateError
from app.features.interview.answer_context import load_answer_context
from app.features.interview.director_service import start_director
from app.features.interview.repository_sources import (
    SourceCollection,
    SourcePreparationError,
    collect_repository_sources,
)
from app.integrations.llm.client import CallBudget
from app.llm_tasks.prompt_loader import (
    PromptConfigurationError,
    PromptNotFoundError,
    load_active_prompt,
)
from app.llm_tasks.repo_deep import analyze_repository, to_repo_analysis_row

STEPS = ("analyze_repo", "build_persona", "set_criteria", "compose_question")
type Sessions = async_sessionmaker[AsyncSession]
type Snapshot = tuple[tuple[UUID, str, bool, UUID], ...]


@dataclass(frozen=True)
class PreparedRepository:
    scope: EvidenceScope
    shallow: c.ShallowRepoAnalysis
    cached: c.DeepRepoAnalysis | None
    invalid_cache: tuple[UUID, dict[str, object] | None, list[dict[str, object]] | None] | None


def _steps(completed: int, failed: bool = False) -> list[dict[str, object]]:
    return [
        dict(
            step=step,
            status=(
                "completed"
                if index < completed
                else "failed"
                if failed and index == completed
                else "running"
                if index == completed
                else "pending"
            ),
        )
        for index, step in enumerate(STEPS)
    ]


async def _owned(db: AsyncSession, user_id: UUID, interview_id: UUID) -> InterviewSession | None:
    row: InterviewSession | None = await db.scalar(
        select(InterviewSession)
        .join(User, User.id == InterviewSession.user_id)
        .where(
            InterviewSession.id == interview_id,
            InterviewSession.user_id == user_id,
            User.status == "active",
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return row


async def _claim(
    sessions: Sessions, user_id: UUID, interview_id: UUID, job_id: UUID
) -> bool | None:
    async with sessions.begin() as db:
        row = await _owned(db, user_id, interview_id)
        if row is None or row.status != "preparing":
            return None
        first = await db.scalar(
            select(InterviewTurn).where(
                InterviewTurn.interview_session_id == interview_id, InterviewTurn.turn_no == 1
            )
        )
        if first is not None:
            try:
                await load_answer_context(
                    db,
                    user_id=user_id,
                    interview_id=interview_id,
                    turn_no=1,
                    limits=c.ContextLimits(2, 0, "director-runtime.v1"),
                    lock=True,
                )
                valid = (
                    row.current_turn == 1
                    and first.persona == "hr_manager"
                    and first.status == "asked"
                    and first.answer_text is None
                    and bool(first.question_text.strip())
                )
            except (c.ContractError, AgentStateError):
                valid = False
            if not valid:
                row.status, row.prepare_steps = "preparing_failed", _steps(3, failed=True)
                row.last_error = dict(
                    reason="prep_failed",
                    code="prepared_question_invalid",
                    step="compose_question",
                    recoverable=True,
                    occurredAt=datetime.now(UTC).isoformat(),
                )
                row.context_state = {
                    key: value
                    for key, value in (row.context_state or {}).items()
                    if key != "prepare_job_id"
                }
                return None
            # 질문 commit 후 상태 전이 전에 중단된 작업은 같은 질문으로 복구한다.
            row.status, row.prepare_steps, row.last_error = "in_progress", _steps(4), None
            row.started_at = row.started_at or datetime.now(UTC)
            row.context_state = {
                key: value
                for key, value in (row.context_state or {}).items()
                if key != "prepare_job_id"
            }
            return True
        state = dict(row.context_state or {})
        if state.get("prepare_job_id"):
            return None
        state["prepare_job_id"] = str(job_id)
        row.context_state, row.prepare_steps = state, _steps(0)
        row.last_error = None
        return False


async def _snapshot(
    sessions: Sessions,
    user_id: UUID,
    interview_id: UUID,
    job_id: UUID,
) -> tuple[c.PromptSpec, tuple[PreparedRepository, ...], Snapshot]:
    async with sessions.begin() as db:
        interview = await _owned(db, user_id, interview_id)
        if (
            interview is None
            or interview.status != "preparing"
            or (interview.context_state or {}).get("prepare_job_id") != str(job_id)
        ):
            raise SourcePreparationError("preparation_changed")
        run = await db.get(AnalysisJob, interview.analysis_job_id)
        posting = await db.get(JobPosting, interview.job_posting_id)
        if (
            run is None
            or run.user_id != user_id
            or run.job_type != "analysis_run"
            or run.status not in {"succeeded", "partial"}
            or run.job_posting_id != interview.job_posting_id
            or posting is None
            or posting.parse_status != "succeeded"
        ):
            raise SourcePreparationError("preparation_inputs_unavailable")
        prompt = await load_active_prompt(db, "repo_deep")
        await load_active_prompt(db, "director")
        await load_active_prompt(db, "answer_analysis")
        criteria = (
            await db.scalars(select(ScoreCriterion).where(ScoreCriterion.is_active.is_(True)))
        ).all()
        if {row.score_key for row in criteria} != set(SCORE_KEYS) or any(
            not row.rubric for row in criteria
        ):
            raise SourcePreparationError("score_criteria_unavailable")
        frame = await db.scalar(
            select(DomainQuestionFrame.id).where(
                DomainQuestionFrame.is_active.is_(True),
                DomainQuestionFrame.domain_category == (posting.domain_category or "etc"),
            )
        )
        if frame is None:
            raise SourcePreparationError("domain_frames_unavailable")
        selected = (
            await db.execute(
                select(SessionRepository, Repository)
                .join(Repository, Repository.id == SessionRepository.repository_id)
                .where(SessionRepository.interview_session_id == interview_id)
                .order_by(SessionRepository.display_order.nulls_last(), SessionRepository.id)
                .with_for_update()
            )
        ).all()
        if not 1 <= len(selected) <= 5:
            raise SourcePreparationError("repository_selection_invalid")
        candidates = (
            await db.scalars(
                select(AnalysisRepoCandidate).where(
                    AnalysisRepoCandidate.analysis_job_id == run.id,
                    AnalysisRepoCandidate.repository_id.in_([repo.id for _, repo in selected]),
                    AnalysisRepoCandidate.filter_status == "eligible",
                )
            )
        ).all()
        analyses = (
            await db.scalars(
                select(RepoAnalysis).where(
                    RepoAnalysis.repository_id.in_([repo.id for _, repo in selected])
                )
            )
        ).all()
        by_id, by_repo = (
            {row.id: row for row in analyses},
            {row.repository_id: row for row in candidates},
        )
        repositories: list[PreparedRepository] = []
        snapshot: list[tuple[UUID, str, bool, UUID]] = []
        for index, (selection, repo) in enumerate(selected):
            candidate = by_repo.get(repo.id)
            l1 = None if candidate is None else resolve_bound_analysis(candidate, by_id)
            if repo.user_id != user_id or repo.is_private or not repo.is_accessible or l1 is None:
                raise SourcePreparationError("bound_l1_unavailable")
            shallow = c.decode(c.ShallowRepoAnalysis, l1.result)
            if shallow.repository_id != str(repo.id) or shallow.head_sha != l1.head_sha:
                raise SourcePreparationError("bound_l1_invalid")
            if (
                selection.snapshot_head_sha is not None
                and selection.snapshot_head_sha != l1.head_sha
            ):
                raise SourcePreparationError("repository_snapshot_changed")
            selection.snapshot_head_sha, selection.is_primary = l1.head_sha, index < 2
            snapshot.append((repo.id, l1.head_sha, index < 2, l1.id))
            if index >= 2:
                continue
            cached: c.DeepRepoAnalysis | None = None
            invalid_cache = None
            for row in analyses:
                if (
                    row.repository_id == repo.id
                    and row.analysis_level == "l2"
                    and row.head_sha == l1.head_sha
                    and row.prompt_version == prompt.version
                    and row.status == "succeeded"
                ):
                    try:
                        checked = c.decode(c.DeepAnalysisResult, row.result)
                        value = checked.analysis
                        if (
                            value is not None
                            and value.repository_id == str(repo.id)
                            and value.head_sha == l1.head_sha
                            and 1 <= len(value.notable_areas) <= 5
                            and len({area.path for area in value.notable_areas})
                            == len(value.notable_areas)
                            and all(area.scope == "entire file" for area in value.notable_areas)
                            and tuple(
                                c.decode(c.NotableArea, area) for area in row.notable_areas or ()
                            )
                            == value.notable_areas
                        ):
                            cached = value
                    except c.ContractError:
                        pass
                    if cached is None:
                        invalid_cache = (row.id, row.result, row.notable_areas)
            repositories.append(
                PreparedRepository(
                    EvidenceScope(
                        str(repo.id), repo.github_repo_id, repo.full_name, l1.head_sha, frozenset()
                    ),
                    shallow,
                    cached,
                    invalid_cache,
                )
            )
        return prompt, tuple(repositories), tuple(snapshot)


async def _unchanged(
    db: AsyncSession,
    user_id: UUID,
    interview_id: UUID,
    job_id: UUID,
    snapshot: Snapshot,
) -> InterviewSession | None:
    row = await _owned(db, user_id, interview_id)
    if (
        row is None
        or row.status != "preparing"
        or (row.context_state or {}).get("prepare_job_id") != str(job_id)
    ):
        return None
    selected = (
        await db.execute(
            select(SessionRepository, Repository)
            .join(Repository, Repository.id == SessionRepository.repository_id)
            .where(SessionRepository.interview_session_id == interview_id)
            .order_by(SessionRepository.display_order.nulls_last(), SessionRepository.id)
            .with_for_update()
        )
    ).all()
    if tuple(
        (repo.id, item.snapshot_head_sha, item.is_primary) for item, repo in selected
    ) != tuple(item[:3] for item in snapshot) or any(
        repo.user_id != user_id or repo.is_private or not repo.is_accessible for _, repo in selected
    ):
        return None
    candidates = (
        await db.scalars(
            select(AnalysisRepoCandidate).where(
                AnalysisRepoCandidate.analysis_job_id == row.analysis_job_id,
                AnalysisRepoCandidate.filter_status == "eligible",
            )
        )
    ).all()
    analyses = (
        await db.scalars(
            select(RepoAnalysis).where(
                RepoAnalysis.id.in_([item[3] for item in snapshot]),
            )
        )
    ).all()
    by_repo, by_id = (
        {item.repository_id: item for item in candidates},
        {item.id: item for item in analyses},
    )
    for repository_id, sha, _, analysis_id in snapshot:
        candidate = by_repo.get(repository_id)
        bound = None if candidate is None else resolve_bound_analysis(candidate, by_id)
        if bound is None or bound.id != analysis_id or bound.head_sha != sha:
            return None
    return row


async def _fail(
    sessions: Sessions,
    user_id: UUID,
    interview_id: UUID,
    job_id: UUID,
    code: str,
    step: str,
) -> None:
    async with sessions.begin() as db:
        row = await _owned(db, user_id, interview_id)
        if (
            row is None
            or row.status != "preparing"
            or (row.context_state or {}).get("prepare_job_id") != str(job_id)
        ):
            return
        _mark_failed(row, code, step)


def _mark_failed(row: InterviewSession, code: str, step: str) -> None:
    row.status, row.prepare_steps = "preparing_failed", _steps(STEPS.index(step), failed=True)
    row.context_state = {
        key: value for key, value in (row.context_state or {}).items() if key != "prepare_job_id"
    }
    row.last_error = dict(
        reason="prep_failed",
        code=code,
        step=step,
        recoverable=True,
        occurredAt=datetime.now(UTC).isoformat(),
    )


async def _release_stale(
    db: AsyncSession,
    user_id: UUID,
    interview_id: UUID,
    job_id: UUID,
    step: str,
) -> None:
    row = await _owned(db, user_id, interview_id)
    if (
        row is not None
        and row.status == "preparing"
        and (row.context_state or {}).get("prepare_job_id") == str(job_id)
    ):
        _mark_failed(row, "preparation_changed", step)
