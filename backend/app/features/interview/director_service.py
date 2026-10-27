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


async def _replay(
    db: AsyncSession,
    interview: InterviewSession,
    record: LLMCallRecord | None,
    turn_no: int,
    call_id: UUID,
    *,
    accepted: bool = False,
) -> AnswerExecution:
    current = await db.scalar(
        select(InterviewTurn).where(
            InterviewTurn.interview_session_id == interview.id,
            InterviewTurn.turn_no == turn_no,
        )
    )
    following = await db.scalar(
        select(InterviewTurn.id).where(
            InterviewTurn.interview_session_id == interview.id,
            InterviewTurn.turn_no == turn_no + 1,
        )
    )
    outcome = _outcome(record) if record is not None else None
    director_record = await db.get(LLMCallRecord, uuid5(call_id, "director"))
    if director_record is not None:
        if (
            director_record.interview_session_id != interview.id
            or director_record.task_name != "director"
        ):
            raise AgentStateError("call_scope_mismatch")
        if not _finished(director_record):
            raise AgentStateError("call_in_progress")
        outcome = _outcome(director_record)
    return AnswerExecution(
        call_id,
        current.id if current else None,
        following,
        interview.status == "completed",
        outcome.failure if outcome else None,
        outcome.discard_reason if outcome else "answer_already_saved",
        accepted,
    )


async def _evaluation_rows(
    db: AsyncSession,
    turn_id: UUID,
    checked: c.ContractChecked[c.AnswerAnalysis],
    evidence: tuple[c.Evidence, ...],
) -> None:
    analysis = checked.data
    by_id = {item.evidence_id: item for item in evidence if item.evidence_id}
    refs = set(analysis.technical_assessment.evidence_refs)
    refs.update(ref for claim in analysis.claim_checks for ref in claim.evidence_refs)
    linked = set(
        await db.scalars(
            select(TurnEvidence.evidence_id).where(
                TurnEvidence.turn_id == turn_id,
                TurnEvidence.usage == "evaluation_basis",
            )
        )
    )
    for ref in refs:
        if UUID(ref) not in linked:
            db.add(TurnEvidence(turn_id=turn_id, evidence_id=UUID(ref), usage="evaluation_basis"))
    conflicts = {
        (row.evidence_id, row.claim_text)
        for row in await db.scalars(
            select(EvidenceConflict).where(EvidenceConflict.turn_id == turn_id)
        )
    }
    for claim in analysis.claim_checks:
        if claim.status == "conflicting":
            for ref in claim.evidence_refs:
                if (UUID(ref), claim.claim_text) in conflicts:
                    continue
                db.add(
                    EvidenceConflict(
                        turn_id=turn_id,
                        evidence_id=UUID(ref),
                        source="answer_vs_code",
                        claim_text=claim.claim_text,
                        evidence_text=by_id[ref].content,
                        verdict="unresolved",
                    )
                )
                conflicts.add((UUID(ref), claim.claim_text))


async def process_answer(
    sessions: async_sessionmaker[AsyncSession],
    *,
    user_id: UUID,
    interview_id: UUID,
    turn_no: int,
    text: str,
    call_id: UUID,
    settings: LLMSettings,
    http_client: httpx.AsyncClient | None = None,
    limits: c.ContextLimits = DEFAULT_LIMITS,
    evidence_limits: EvidenceLimits | None = None,
    on_answer_saved: Callable[[], Awaitable[None]] | None = None,
    on_evidence_check: Callable[[tuple[c.Evidence, ...]], Awaitable[None]] | None = None,
) -> AnswerExecution:
    """답변을 먼저 확정하고 T3·제한 조회·T4를 수행한다. 마지막 T3 성공 후에만 완료한다."""
    if type(text) is not str or not text.strip():
        raise AgentStateError("answer_text_invalid")
    async with sessions.begin() as db:
        interview = await _owned(db, user_id, interview_id)
        record = await db.get(LLMCallRecord, call_id)
        if record is not None:
            if (
                record.interview_session_id != interview_id
                or record.task_name != "answer_analysis"
                or record.turn_no != turn_no
            ):
                raise AgentStateError("call_scope_mismatch")
            if not (record.turn_id or record.failure or record.discard_reason):
                raise AgentStateError("call_in_progress")
            return await _replay(db, interview, record, turn_no, call_id)
        if interview.status != "in_progress" or interview.current_turn != turn_no:
            raise AgentStateError("answer_turn_invalid")
        loaded = await load_answer_context(
            db,
            user_id=user_id,
            interview_id=interview_id,
            turn_no=turn_no,
            limits=limits,
            lock=True,
        )
        turn = await db.get(InterviewTurn, UUID(loaded.turn_id))
        assert turn is not None
        if turn.status == "answered":
            return await _replay(db, interview, None, turn_no, call_id)
        await _pending(db, interview_id, turn_no, "answer_analysis")
        prompt = await load_active_prompt(db, "answer_analysis")
        scopes = [
            await load_evidence_scope(
                db,
                user_id=user_id,
                interview_id=interview_id,
                repository_id=UUID(repo.repository_id),
            )
            for repo in loaded.context.repositories
        ]
        locations = frozenset(
            (scope.repository_id, scope.git_ref, path)
            for scope in scopes
            for path in scope.allowed_paths
        )
        now = datetime.now(UTC)
        turn.answer_text, turn.status, turn.answered_at = text, "answered", now
        if turn.asked_at is not None:
            turn.answer_duration_sec = max(0, int((now - turn.asked_at).total_seconds()))
        db.add(
            LLMCallRecord(
                id=call_id,
                interview_session_id=interview_id,
                turn_no=turn_no,
                task_name="answer_analysis",
                attempts=[],
            )
        )
    attempts: list[c.AttemptMetadata] = []
    budget = CallBudget()
    try:
        if on_answer_saved is not None:
            await on_answer_saved()
        initial = await analyze_answer(
            loaded.context,
            loaded.question,
            turn_id=loaded.turn_id,
            answer_text=text,
            prompt=prompt,
            settings=settings,
            budget=budget,
            allowed_locations=locations,
            http_client=http_client,
            attempt_sink=attempts,
        )
        async with sessions.begin() as db:
            record = await db.get(LLMCallRecord, call_id, with_for_update=True)
            assert record is not None
            record.attempts = [asdict(item) for item in attempts]
            record.failure = asdict(initial.failure) if initial.failure else None
            if initial.failure:
                return AnswerExecution(
                    call_id, UUID(loaded.turn_id), None, False, initial.failure, None, True
                )
            try:
                current = await load_answer_context(
                    db,
                    user_id=user_id,
                    interview_id=interview_id,
                    turn_no=turn_no,
                    limits=limits,
                    lock=True,
                )
                valid = current.context == loaded.context and current.answer_text == text
            except AgentStateError:
                valid = False
            if not valid:
                record.discard_reason = "context_changed"
                return AnswerExecution(
                    call_id, UUID(loaded.turn_id), None, False, None, "context_changed", True
                )
            assert initial.data is not None
            turn = await db.get(InterviewTurn, UUID(loaded.turn_id))
            assert turn is not None
            if turn.analysis is None:
                turn.analysis = c.to_data(initial.data)
                await _evaluation_rows(db, turn.id, initial.data, loaded.context.evidence)
        selected = initial.data
        tool_result, summary = await _retrieve(
            sessions,
            user_id,
            interview_id,
            loaded.context,
            selected,
            locations,
            scopes,
            evidence_limits,
            http_client,
            on_evidence_check,
        )
        final_evidence = loaded.context.evidence
        if tool_result is not None:
            final_evidence += tool_result.items
            # 같은 T3 예산을 사용한다. 최초 호출이 재시도했다면 추가 provider 호출은 없다.
            enriched = await analyze_answer(
                loaded.context,
                loaded.question,
                turn_id=loaded.turn_id,
                answer_text=text,
                prompt=prompt,
                settings=settings,
                budget=budget,
                tool_results=(tool_result,),
                allowed_locations=locations,
                http_client=http_client,
                attempt_sink=attempts,
            )
            if enriched.data is not None:
                selected = enriched.data
            elif enriched.failure is not None:
                summary += (
                    "\n보강 분석 미완료: "
                    + enriched.failure.stage
                    + "/"
                    + enriched.failure.error_code
                )
                async with sessions.begin() as db:
                    record = await db.get(LLMCallRecord, call_id, with_for_update=True)
                    assert record is not None
                    record.attempts = [asdict(item) for item in attempts]
                    record.failure = asdict(enriched.failure)
                    record.turn_id = UUID(loaded.turn_id)
                    turn = await db.get(InterviewTurn, UUID(loaded.turn_id))
                    if turn is not None and turn.decision is not None:
                        turn.decision = {**turn.decision, "reason_summary": summary}
                return AnswerExecution(
                    call_id, UUID(loaded.turn_id), None, False, enriched.failure, None, True
                )
        async with sessions.begin() as db:
            record = await db.get(LLMCallRecord, call_id, with_for_update=True)
            assert record is not None
            record.attempts = [asdict(item) for item in attempts]
            try:
                interview = await _owned(db, user_id, interview_id)
                current = await load_answer_context(
                    db,
                    user_id=user_id,
                    interview_id=interview_id,
                    turn_no=turn_no,
                    limits=limits,
                    lock=True,
                )
                valid = (
                    replace(current.context, evidence=loaded.context.evidence) == loaded.context
                    and frozenset(current.context.evidence) == frozenset(final_evidence)
                    and current.answer_text == text
                )
            except AgentStateError:
                valid = False
            if not valid:
                record.discard_reason = "context_changed"
                return AnswerExecution(
                    call_id, UUID(loaded.turn_id), None, False, None, "context_changed", True
                )
            turn = await db.get(InterviewTurn, UUID(loaded.turn_id))
            assert turn is not None
            await _evaluation_rows(db, turn.id, selected, final_evidence)
            if turn_no == 9:
                decision = c.validate_decision(
                    c.DirectorDecision(
                        "finish",
                        "정상 면접 완료",
                        None,
                        None,
                        (),
                        "9번째 확정 답변 분석 완료" + ("\n" + summary if summary else ""),
                    ),
                    question=None,
                    allowed_personas=(),
                    finish_allowed=True,
                    allowed_locations=locations,
                )
                turn.decision = c.to_data(decision)
                interview.status, interview.completed_at = "completed", datetime.now(UTC)
                _save_context_snapshot(interview, current.context, turn, turn, phase="completed")
            elif summary:
                from devon_ai.agents.director.runtime import verification_decision

                lookup = verification_decision(
                    loaded.context, initial.data, allowed_locations=locations
                )
                if lookup is not None:
                    turn.decision = asdict(
                        replace(
                            lookup.data, reason_summary=lookup.data.reason_summary + "\n" + summary
                        )
                    )
            record.turn_id = turn.id
        if turn_no == 9:
            return AnswerExecution(call_id, UUID(loaded.turn_id), None, True, None, None, True)
        question = await start_director(
            sessions,
            user_id=user_id,
            interview_id=interview_id,
            call_id=uuid5(call_id, "director"),
            settings=settings,
            http_client=http_client,
            limits=limits,
            answer_analysis=selected,
            lookup_summary=summary,
            tool_results=() if tool_result is None else (tool_result,),
        )
        return AnswerExecution(
            call_id,
            UUID(loaded.turn_id),
            question.turn_id,
            False,
            question.failure,
            question.discard_reason,
            True,
        )
    except (asyncio.CancelledError, Exception) as error:
        await _close_claim(sessions, call_id, attempts, error)
        raise


async def _retrieve(
    sessions: async_sessionmaker[AsyncSession],
    user_id: UUID,
    interview_id: UUID,
    context: c.Context,
    analysis: c.ContractChecked[c.AnswerAnalysis],
    locations: frozenset[tuple[str, str, str]],
    scopes: list[EvidenceScope],
    evidence_limits: EvidenceLimits | None,
    http_client: httpx.AsyncClient | None,
    on_evidence_check: Callable[[tuple[c.Evidence, ...]], Awaitable[None]] | None,
) -> tuple[c.ToolResult | None, str]:
    from devon_ai.agents.director.runtime import verification_decision

    decision = verification_decision(context, analysis, allowed_locations=locations)
    if decision is None:
        return None, ""
    assert context.current_turn_id is not None
    request = decision.data.tool_requests[0]
    requested = f"{request.repository_id}@{request.git_ref}: " + ", ".join(request.allowed_paths)
    # 미실행 요청은 실제 조회 결과와 구분해 범위와 상한 사유를 보존한다.
    unexecuted = tuple(
        f"미조회: {item.repository_id}@{item.git_ref}: "
        + ", ".join(item.allowed_paths)
        + "; 이유: 턴당 1개 조회 제한"
        for item in decision.data.tool_requests[1:]
    )
    unexecuted_summary = "; 한계: " + "; ".join(unexecuted) if unexecuted else ""

    async def remember(summary: str) -> None:
        async with sessions.begin() as db:
            await _owned(db, user_id, interview_id)
            turn = await db.get(InterviewTurn, UUID(context.current_turn_id), with_for_update=True)
            if turn is not None:
                turn.decision = asdict(replace(decision.data, reason_summary=summary))

    await remember("근거 조회 요청; 실제 확인 아직 없음; 요청: " + requested + unexecuted_summary)
    limits = evidence_limits
    if limits is None:
        config = get_settings()
        limits = EvidenceLimits(
            config.director_evidence_max_requests,
            config.director_evidence_max_files,
            config.director_evidence_max_response_bytes,
            config.director_evidence_max_total_bytes,
            config.director_evidence_timeout_seconds,
        )
    scope = next(scope for scope in scopes if scope.repository_id == request.repository_id)

    async def execute(http: httpx.AsyncClient) -> c.ToolResult:
        return await read_files(
            request, scope=scope, paths=request.allowed_paths, limits=limits, http_client=http
        )

    try:
        if http_client is None:
            async with httpx.AsyncClient(follow_redirects=False) as http:
                result = await execute(http)
        else:
            result = await execute(http_client)
    except asyncio.CancelledError:
        await remember(
            "근거 조회 중단; 완료된 확인 범위 없음; 요청: " + requested + unexecuted_summary
        )
        raise
    async with sessions.begin() as db:
        stored = await store_evidence(
            db, user_id=user_id, interview_id=interview_id, items=result.items
        )
        if stored:
            await db.execute(
                update(Evidence)
                .where(
                    Evidence.id.in_(
                        [UUID(item.evidence_id) for item in stored if item.evidence_id]
                    ),
                )
                .values(retrieved_for_turn=context.turn_no)
            )
    result = replace(result, items=stored, limitations=result.limitations + unexecuted)
    summary = "근거 조회 " + result.status + "; 실제 확인: " + ", ".join(result.searched_scope)
    summary += "; 요청: " + requested
    if result.error_code:
        summary += "; 오류: " + result.error_code
    if result.limitations:
        summary += "; 한계: " + "; ".join(result.limitations)
    await remember(summary)
    if stored and on_evidence_check is not None:
        await on_evidence_check(stored)
    return result, summary
