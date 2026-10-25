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
