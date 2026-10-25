"""답변 분석·제한 근거 조회·자동 Director의 영구 저장 경계."""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4, uuid5

import httpx
from devon_ai import contracts as c
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.director.agent import execute_director
from app.agents.director.tools import EvidenceLimits, EvidenceScope, read_files
from app.core.config import LLMSettings, get_settings
from app.db.models import (
    Evidence,
    EvidenceConflict,
    InterviewSession,
    InterviewTurn,
    LLMCallRecord,
    TurnEvidence,
)
from app.features.interview.agent_context import AgentStateError, load_context
from app.features.interview.agent_queries import load_evidence_scope, store_evidence
from app.features.interview.agent_service import QuestionExecution, _finished, _outcome, _owned
from app.features.interview.answer_context import (
    load_answer_context,
    prior_analyses,
    reference_texts,
)
from app.integrations.llm.client import CallBudget
from app.llm_tasks.answer_analysis import analyze_answer
from app.llm_tasks.prompt_loader import load_active_prompt

DEFAULT_LIMITS = c.ContextLimits(2, 0, "director-runtime.v1")


@dataclass(frozen=True)
class AnswerExecution:
    call_id: UUID
    turn_id: UUID | None
    next_turn_id: UUID | None
    completed: bool
    failure: c.CallFailure | None
    discard_reason: str | None
    accepted: bool


def _save_context_snapshot(
    interview: InterviewSession,
    context: c.Context,
    turn: InterviewTurn,
    decision_turn: InterviewTurn,
    *,
    phase: Literal["awaiting_answer", "completed"],
) -> None:
    """준비 작업의 상태를 보존하고 DB에서 확정한 현재 턴·판단의 작은 스냅샷을 갱신한다."""
    interview.context_state = {
        **(interview.context_state or {}),
        "director": {
            "phase": phase,
            "current_turn_id": str(turn.id),
            "turn_no": turn.turn_no,
            "total_turns": context.total_turns,
            "question_contract": turn.question_contract,
            "decision_turn_id": str(decision_turn.id),
            "decision": decision_turn.decision,
            "analysis_ref": str(decision_turn.id) if decision_turn.analysis is not None else None,
            "persona_counts": {
                item.persona: item.count + int(item.persona == turn.persona)
                for item in context.persona_counts
            },
            "repositories": [asdict(repo) for repo in context.repositories],
            "evidence_refs": [item.evidence_id for item in context.evidence if item.evidence_id],
            "history_analysis_refs": [
                {"turn_id": item.turn_id, "analysis_ref": item.analysis_ref}
                for item in context.history
            ],
        },
    }


async def _pending(db: AsyncSession, interview_id: UUID, turn_no: int, task: str) -> None:
    if await db.scalar(
        select(LLMCallRecord.id).where(
            LLMCallRecord.interview_session_id == interview_id,
            LLMCallRecord.turn_no == turn_no,
            LLMCallRecord.task_name == task,
            LLMCallRecord.turn_id.is_(None),
            LLMCallRecord.failure.is_(None),
            LLMCallRecord.discard_reason.is_(None),
        )
    ):
        raise AgentStateError("call_in_progress")


async def _close_claim(
    sessions: async_sessionmaker[AsyncSession],
    call_id: UUID,
    attempts: list[c.AttemptMetadata],
    error: BaseException,
) -> None:
    async with sessions.begin() as db:
        record = await db.get(LLMCallRecord, call_id, with_for_update=True)
        if record is not None and record.turn_id is None and record.failure is None:
            record.attempts = [asdict(attempt) for attempt in attempts]
            record.discard_reason = (
                "canceled" if isinstance(error, asyncio.CancelledError) else "execution_error"
            )


async def start_director(
    sessions: async_sessionmaker[AsyncSession],
    *,
    user_id: UUID,
    interview_id: UUID,
    call_id: UUID,
    settings: LLMSettings,
    http_client: httpx.AsyncClient | None = None,
    limits: c.ContextLimits = DEFAULT_LIMITS,
    answer_analysis: c.ContractChecked[c.AnswerAnalysis] | None = None,
    lookup_summary: str = "",
    tool_results: tuple[c.ToolResult, ...] = (),
) -> QuestionExecution:
    """DB에서 확정한 입력으로 질문을 만들고 저장한다. 공개 전송·준비 완료는 호출자 책임이다."""
    async with sessions.begin() as db:
        await _owned(db, user_id, interview_id)
        existing = await db.get(LLMCallRecord, call_id)
        if existing is not None:
            if existing.interview_session_id != interview_id or existing.task_name != "director":
                raise AgentStateError("call_scope_mismatch")
            if not _finished(existing):
                raise AgentStateError("call_in_progress")
            return _outcome(existing)
        context = await load_context(db, user_id=user_id, interview_id=interview_id, limits=limits)
        await _pending(db, interview_id, context.turn_no, "director")
        prompt = await load_active_prompt(db, "director")
        sources = await reference_texts(db, interview_id)
        past = await prior_analyses(db, context)
        db.add(
            LLMCallRecord(
                id=call_id,
                interview_session_id=interview_id,
                turn_no=context.turn_no,
                task_name="director",
                attempts=[],
            )
        )
    attempts: list[c.AttemptMetadata] = []
    try:
        result = await execute_director(
            context,
            prompt=prompt,
            settings=settings,
            budget=CallBudget(),
            answer_analysis=answer_analysis,
            reference_texts=sources,
            prior_analyses=past,
            tool_results=tool_results,
            http_client=http_client,
            attempt_sink=attempts,
        )
        async with sessions.begin() as db:
            record = await db.get(LLMCallRecord, call_id, with_for_update=True)
            if record is None:
                raise AgentStateError("call_unavailable")
            record.attempts = [asdict(attempt) for attempt in result.attempts]
            record.failure = asdict(result.failure) if result.failure else None
            if result.failure is not None:
                return _outcome(record)
            try:
                interview = await _owned(db, user_id, interview_id)
                current = await load_context(
                    db, user_id=user_id, interview_id=interview_id, limits=limits, lock=True
                )
                unchanged = (
                    current == context
                    and await reference_texts(db, interview_id) == sources
                    and await prior_analyses(db, current) == past
                )
            except (AgentStateError, c.ContractError):
                unchanged = False
            if not unchanged:
                record.discard_reason = "context_changed"
                return _outcome(record)
            assert result.data is not None
            outcome = result.data
            if outcome.question is None or outcome.generation is None:
                record.discard_reason = "question_missing"
                return _outcome(record)
            question = outcome.question.data
            if len(question.topic_code) > 50:
                record.discard_reason = "question_storage_invalid"
                return _outcome(record)
            metadata = outcome.generation
            turn = InterviewTurn(
                id=uuid4(),
                interview_session_id=interview_id,
                turn_no=context.turn_no,
                persona=question.persona,
                question_text=question.text,
                question_contract=asdict(question.question_contract),
                topic_code=question.topic_code,
                jd_requirement_ids=[UUID(value) for value in question.jd_requirement_ids],
                model=metadata.model,
                prompt_version=metadata.prompt_version,
                asked_at=datetime.now(UTC),
            )
            db.add(turn)
            await db.flush()
            db.add_all(
                TurnEvidence(turn_id=turn.id, evidence_id=UUID(value), usage="question_basis")
                for value in question.evidence_refs
            )
            decision = outcome.decision.data
            if lookup_summary:
                decision = replace(
                    decision, reason_summary=decision.reason_summary + "\n" + lookup_summary
                )
            previous = (
                await db.get(InterviewTurn, UUID(context.current_turn_id))
                if context.current_turn_id
                else turn
            )
            if previous is not None:
                previous.decision = asdict(decision)
                _save_context_snapshot(interview, context, turn, previous, phase="awaiting_answer")
            interview.current_turn = context.turn_no
            record.turn_id = turn.id
            return _outcome(record)
    except (asyncio.CancelledError, Exception) as error:
        await _close_claim(sessions, call_id, attempts, error)
        raise
