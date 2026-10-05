"""준비된 질문 계약의 호출·저장 경계. WS·자동 목적 선정은 호출자가 담당한다."""

import asyncio
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

import httpx
from devon_ai import contracts as c
from devon_ai.agents.director.agent import QuestionReviewer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.contracts import to_turn_jsonb
from app.agents.director.agent import generate_question
from app.core.config import LLMSettings, get_settings
from app.db.models import InterviewSession, InterviewTurn, LLMCallRecord, TurnEvidence, User
from app.features.interview.agent_context import AgentStateError, load_context
from app.integrations.llm.client import CallBudget
from app.llm_tasks.prompt_loader import load_active_prompt


@dataclass(frozen=True)
class QuestionExecution:
    """호출자의 후속 처리를 위한 식별자. 모델 원문은 내부 DB 기록에만 남긴다."""

    call_id: UUID
    turn_id: UUID | None
    failure: c.CallFailure | None
    discard_reason: str | None


def _outcome(record: LLMCallRecord) -> QuestionExecution:
    failure = record.failure
    return QuestionExecution(
        record.id,
        record.turn_id,
        None
        if failure is None
        else c.CallFailure(
            stage=cast(c.CallFailureStage, failure["stage"]),
            error_code=cast(str, failure["error_code"]),
            reason_summary=cast(str, failure["reason_summary"]),
        ),
        record.discard_reason,
    )


async def _owned(
    db: AsyncSession,
    user_id: UUID,
    interview_id: UUID,
) -> InterviewSession:
    interview = await db.scalar(
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
    if interview is None:
        raise AgentStateError("interview_unavailable")
    return interview


def _finished(record: LLMCallRecord) -> bool:
    return bool(record.turn_id or record.failure or record.discard_reason or record.attempts)


async def generate_prepared_question(
    sessions: async_sessionmaker[AsyncSession],
    *,
    user_id: UUID,
    interview_id: UUID,
    call_id: UUID,
    question_contract: c.QuestionContract,
    review: QuestionReviewer,
    settings: LLMSettings,
    limits: c.ContextLimits,
    budget: CallBudget,
    http_client: httpx.AsyncClient | None = None,
) -> QuestionExecution:
    """DB 원본을 읽고 transaction 밖에서 모델을 호출한 뒤 원본을 재검사한다.

    call_id는 호출자가 논리 작업 전에 발급하며 같은 요청을 다시 전달할 때 재사용한다.
    진행 중인 호출은 중복 실행하지 않는다. 준비된 계약·실제 reviewer가 없으면 호출할
    수 없으며 자동 Director·준비 워커·T3/T4/WS를 대신하지 않는다.
    """
    if type(question_contract) is not c.QuestionContract:
        raise c.ContractError("schema", "question_contract")
    # 생성 전과 저장 직전의 Context를 같은 검증된 배분으로 계산한다.
    quota = dict(get_settings().persona_turn_quota)
    async with sessions.begin() as db:
        await _owned(db, user_id, interview_id)
        existing = await db.get(LLMCallRecord, call_id)
        if existing is not None:
            if existing.interview_session_id != interview_id or existing.task_name != "director":
                raise AgentStateError("call_scope_mismatch")
            if not _finished(existing):
                raise AgentStateError("call_in_progress")
            return _outcome(existing)
        context = await load_context(
            db, user_id=user_id, interview_id=interview_id, limits=limits, quota=quota
        )
        pending = await db.scalar(
            select(LLMCallRecord.id).where(
                LLMCallRecord.interview_session_id == interview_id,
                LLMCallRecord.turn_no == context.turn_no,
                LLMCallRecord.task_name == "director",
                LLMCallRecord.turn_id.is_(None),
                LLMCallRecord.failure.is_(None),
                LLMCallRecord.discard_reason.is_(None),
                LLMCallRecord.attempts == [],
            )
        )
        if pending is not None:
            raise AgentStateError("call_in_progress")
        prompt = await load_active_prompt(db, "director")
        db.add(
            LLMCallRecord(
                id=call_id,
                interview_session_id=interview_id,
                turn_no=context.turn_no,
                task_name="director",
                attempts=[],
            )
        )

    completed_attempts: list[c.AttemptMetadata] = []
    result: c.ModelResult[c.ContractChecked[c.Question]] | None = None
    try:
        result = await generate_question(
            context,
            question_contract,
            prompt=prompt,
            settings=settings,
            budget=budget,
            review=review,
            http_client=http_client,
            attempt_sink=completed_attempts,
        )

        async with sessions.begin() as db:
            # 상태를 재검사할 때 실패 결과도 버리지 않고 내부 호출 기록에 보존한다.
            interview = await db.scalar(
                select(InterviewSession)
                .where(
                    InterviewSession.id == interview_id,
                    InterviewSession.user_id == user_id,
                )
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if interview is None:
                raise AgentStateError("interview_unavailable")
            record = await db.get(LLMCallRecord, call_id, with_for_update=True)
            if record is None:
                raise AgentStateError("call_unavailable")
            if _finished(record):
                return _outcome(record)
            record.attempts = [asdict(attempt) for attempt in result.attempts]
            record.failure = None if result.failure is None else asdict(result.failure)
            if result.failure is not None:
                return _outcome(record)
            try:
                current = await load_context(
                    db,
                    user_id=user_id,
                    interview_id=interview_id,
                    limits=limits,
                    lock=True,
                    quota=quota,
                )
            except (AgentStateError, c.ContractError):
                current = None
            if current != context:
                record.discard_reason = "context_changed"
                return _outcome(record)
            assert result.data is not None  # ModelResult 계약이 성공 값의 존재를 보장한다.
            question = result.data.data
            if len(question.topic_code) > 50:
                record.discard_reason = "question_storage_invalid"
                return _outcome(record)
            metadata = result.attempts[-1]
            turn = InterviewTurn(
                id=uuid4(),
                interview_session_id=interview_id,
                turn_no=context.turn_no,
                persona=question.persona,
                question_text=question.text,
                question_contract=to_turn_jsonb(result, column="question_contract"),
                topic_code=question.topic_code,
                jd_requirement_ids=[UUID(value) for value in question.jd_requirement_ids],
                model=metadata.model,
                prompt_version=metadata.prompt_version,
                asked_at=datetime.now(UTC),
            )
            db.add(turn)
            await db.flush()
            db.add_all(
                [
                    TurnEvidence(turn_id=turn.id, evidence_id=UUID(value), usage="question_basis")
                    for value in question.evidence_refs
                ]
            )
            interview.current_turn = context.turn_no
            record.turn_id = turn.id
            # 질문·contract·근거 관계·호출 기록은 이 transaction에서 함께 commit된다.
            return _outcome(record)
    except (asyncio.CancelledError, Exception) as error:
        # 취소·프로그래밍 오류를 가짜 모델 실패로 변환하지 않는다. 완료 전 claim만 닫는다.
        async with sessions.begin() as db:
            record = await db.get(LLMCallRecord, call_id, with_for_update=True)
            if record is not None and not _finished(record):
                record.attempts = [asdict(attempt) for attempt in completed_attempts]
                if result is not None and result.failure is not None:
                    record.failure = asdict(result.failure)
                record.discard_reason = (
                    "canceled" if isinstance(error, asyncio.CancelledError) else "execution_error"
                )
        raise
