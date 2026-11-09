"""저장된 답변을 보존하는 유한 Director 재생성. STT·T3·L2는 호출하지 않는다."""

import asyncio
import hashlib
import json
import secrets
from collections.abc import Awaitable, Callable, Mapping
from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal, cast
from uuid import UUID, uuid4, uuid5

import httpx
from devon_ai import contracts as c
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import LLMSettings
from app.core.errors import AppError
from app.db.models import InterviewSession, InterviewTurn, LLMCallRecord, PromptVersion
from app.features.interview.agent_context import AgentStateError, load_context
from app.features.interview.agent_service import QuestionExecution, _owned
from app.features.interview.answer_context import prior_analyses, reference_texts
from app.features.interview.schemas import QuestionRetryResponse, QuestionRetryState
from app.shared.enums import Reason

_KEY = "question_retry_v1"
_LIMITS = c.ContextLimits(2, 0, "director-runtime.v1")
_RUNNING: set[asyncio.Task[QuestionExecution]] = set()

# 닫힌 WS의 세션을 바꾸되, 응답 유실 후 같은 requestId는 같은 발급 결과를 재생한다.
_ROTATE = """
local old = redis.call('GET', KEYS[1])
if old and old ~= ARGV[1] then
  local owner = redis.call('GET', 'ws:lock:' .. old)
  if owner then redis.call('PUBLISH', 'ws:replace:' .. old, owner) end
  redis.call('DEL', ARGV[4] .. old)
end
redis.call('SET', ARGV[4] .. ARGV[1], ARGV[2], 'EX', ARGV[3])
redis.call('SET', KEYS[1], ARGV[1], 'EX', ARGV[3])
return 1
"""


@dataclass(frozen=True)
class _Scope:
    target: int
    previous: UUID
    failure: LLMCallRecord
    digest: str
    analysis: c.ContractChecked[c.AnswerAnalysis]
    lookup_summary: str
    tool_results: tuple[c.ToolResult, ...]


def _ledger(row: InterviewSession) -> dict[str, dict[str, object]]:
    raw = (row.context_state or {}).get(_KEY, {})
    if type(raw) is not dict or len(raw) > 16:
        raise AppError(Reason.QUESTION_RETRY_UNAVAILABLE)
    if any(type(key) is not str or type(value) is not dict for key, value in raw.items()):
        raise AppError(Reason.QUESTION_RETRY_UNAVAILABLE)
    return deepcopy(raw)


def _store(row: InterviewSession, ledger: dict[str, dict[str, object]]) -> None:
    row.context_state = {**(row.context_state or {}), _KEY: ledger}


def _expired(entry: Mapping[str, object]) -> bool:
    try:
        value = entry["deadline"]
        return type(value) is not str or datetime.fromisoformat(value) <= datetime.now(UTC)
    except (KeyError, ValueError, TypeError):
        return True


def retryable_failure(failure: object, attempts: object) -> bool:
    """공급자 영구 오류를 새 수동 라운드로 우회하지 않는다."""
    if not isinstance(failure, dict):
        return False
    code, stage = failure.get("error_code"), failure.get("stage")
    if stage == "semantic":
        return code in {
            "director_candidate_rewrite",
            "director_candidate_replan",
            "director_no_valid_candidate",
        }
    cause, status = failure.get("provider_cause"), failure.get("provider_status")
    allowed = failure.get("manual_retryable")
    if cause is not None or status is not None or allowed is not None:
        # 새 기록은 구조 필드만 신뢰한다. 설명 문구·보호된 원문을 정책으로 재해석하지 않는다.
        if allowed is not True:
            return False
        return (
            stage == "timeout" and code == "llm_timeout" and cause == "timeout" and status is None
        ) or (
            stage == "provider"
            and (
                cause == "transport"
                and status is None
                or cause == "transient_http"
                and status in (408, 409, 500, 502, 503, 504)
                or cause == "rate_limit"
                and status == 429
            )
        )
    # 구조 필드가 없던 과거 기록만 기존의 제한된 호환 판정을 사용한다.
    if stage == "timeout":
        return code == "llm_timeout"
    if stage != "provider":
        return False
    reason = failure.get("reason_summary")
    if reason == "Provider transport failed.":
        return True
    if reason in {
        f"Provider HTTP {status} request failed." for status in (408, 409, 500, 502, 503, 504)
    }:
        return True
    if reason != "Provider HTTP 429 request failed." or not isinstance(attempts, list):
        return False
    # 429는 quota와 일시적 rate limit을 구분할 수 있을 때만 허용한다.
    for item in attempts:
        if not isinstance(item, dict) or not isinstance(item.get("raw_output"), str):
            continue
        try:
            body = json.loads(item["raw_output"])
        except (ValueError, TypeError):
            return False
        error = body.get("error") if isinstance(body, dict) else None
        if not isinstance(error, dict):
            return False
        if error.get("code") in {
            "insufficient_quota",
            "credit_balance_exhausted",
            "billing_limit_exceeded",
            "organization_usage_limit_exceeded",
        }:
            return False
        if error.get("code") == "rate_limit_exceeded" or error.get("type") == "rate_limit_error":
            return True
    return False


def progress(row: InterviewSession) -> QuestionRetryState | None:
    """새로고침은 저장된 수동 요청 ID를 복원하며 새 라운드를 소비하지 않는다."""
    if row.status != "in_progress":
        return None
    candidates = [
        entry
        for entry in _ledger(row).values()
        if entry.get("kind") == "manual"
        and entry.get("target") in {row.current_turn, row.current_turn + 1}
    ]
    if not candidates:
        return None
    entry = max(candidates, key=lambda item: int(str(item["target"])))
    try:
        effective = entry
        child_id = str(uuid5(UUID(str(entry["call_id"])), "automatic-rewrite"))
        child = _ledger(row).get(child_id)
        if child is not None and (
            child.get("kind") == "auto"
            and child.get("failed_call_id") == entry.get("call_id")
            and child.get("target") == entry.get("target")
            and child.get("previous_turn_id") == entry.get("previous_turn_id")
            and child.get("binding") == entry.get("binding")
        ):
            effective = child
        status = effective.get("status")
        if status not in {"running", "succeeded", "failed"}:
            return None
        if status == "running" and _expired(effective):
            status = "failed"
        return QuestionRetryState(
            request_id=UUID(str(entry["request_id"])),
            turn_no=int(str(entry["target"])),
            status=status,
            expires_at=datetime.fromisoformat(str(effective["deadline"])),
        )
    except (KeyError, ValueError, TypeError):
        return None


async def _scope(db: AsyncSession, row: InterviewSession) -> _Scope:
    if row.status != "in_progress" or not 1 <= row.current_turn < row.total_turns:
        raise AppError(Reason.QUESTION_RETRY_UNAVAILABLE)
    target = row.current_turn + 1
    if await db.scalar(
        select(InterviewTurn.id).where(
            InterviewTurn.interview_session_id == row.id, InterviewTurn.turn_no == target
        )
    ):
        raise AppError(Reason.QUESTION_RETRY_UNAVAILABLE)
    previous = await db.scalar(
        select(InterviewTurn).where(
            InterviewTurn.interview_session_id == row.id, InterviewTurn.turn_no == row.current_turn
        )
    )
    if (
        previous is None
        or previous.status != "answered"
        or not previous.answer_text
        or previous.analysis is None
    ):
        raise AppError(Reason.QUESTION_RETRY_UNAVAILABLE)
    # JSONB null과 SQL NULL을 실패로 혼동하지 않고 실제 실패 객체만 선택한다.
    records = list(
        await db.scalars(
            select(LLMCallRecord)
            .where(
                LLMCallRecord.interview_session_id == row.id,
                LLMCallRecord.task_name == "director",
                LLMCallRecord.turn_no == target,
            )
            .order_by(LLMCallRecord.created_at.desc(), LLMCallRecord.id.desc())
        )
    )
    failed = next(
        (
            item
            for item in records
            if type(item.failure) is dict and item.discard_reason is None and item.turn_id is None
        ),
        None,
    )
    if failed is None or not retryable_failure(failed.failure, failed.attempts):
        raise AppError(Reason.QUESTION_RETRY_UNAVAILABLE)
    successful_t3 = list(
        await db.scalars(
            select(LLMCallRecord).where(
                LLMCallRecord.interview_session_id == row.id,
                LLMCallRecord.task_name == "answer_analysis",
                LLMCallRecord.turn_id == previous.id,
            )
        )
    )
    if not any(
        item.failure is None and item.discard_reason is None and item.attempts
        for item in successful_t3
    ):
        raise AppError(Reason.QUESTION_RETRY_UNAVAILABLE)
    context = await load_context(db, user_id=row.user_id, interview_id=row.id, limits=_LIMITS)
    past = await prior_analyses(db, context)
    checked = past.get(str(previous.id))
    if checked is None:
        raise AppError(Reason.QUESTION_RETRY_UNAVAILABLE)
    sources = await reference_texts(db, row.id)
    prompt = await db.scalar(
        select(PromptVersion).where(
            PromptVersion.task_name == "director", PromptVersion.is_active.is_(True)
        )
    )
    stored_inputs = (row.context_state or {}).get("director_retry_inputs", {})
    saved = stored_inputs.get(str(target)) if isinstance(stored_inputs, dict) else None
    if isinstance(saved, dict):
        summary = saved.get("lookup_summary", "")
        raw_tools = saved.get("tool_results", [])
    else:
        summary = (previous.decision or {}).get("reason_summary", "")
        traces = (row.context_state or {}).get("evidence_tool_results", {})
        trace = traces.get(str(previous.id)) if isinstance(traces, dict) else None
        raw_tools = [] if trace is None else [trace]
    if not isinstance(summary, str) or not isinstance(raw_tools, list):
        raise AppError(Reason.QUESTION_RETRY_UNAVAILABLE)
    tools = tuple(c.decode(c.ToolResult, value) for value in raw_tools)
    binding = {
        "lookup_summary": summary,
        "tool_results": [asdict(value) for value in tools],
        "context": asdict(context),
        "analysis": asdict(checked.data),
        "sources": sorted((ref.kind, ref.id, text) for ref, text in sources.items()),
        "prompt": None
        if prompt is None
        else (str(prompt.id), prompt.version, prompt.model, prompt.template),
    }
    digest = hashlib.sha256(
        json.dumps(binding, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()
    return _Scope(target, previous.id, failed, digest, checked, summary, tools)


async def availability(db: AsyncSession, row: InterviewSession) -> tuple[bool, int]:
    """GET은 복구를 실행하지 않고 검증된 저장 상태와 수동 횟수만 보여 준다."""
    try:
        ledger = _ledger(row)
        target = row.current_turn + 1
        current = [entry for entry in ledger.values() if entry.get("target") == target]
        count = sum(entry.get("kind") == "manual" for entry in current)
        if count or any(
            entry.get("status") == "running" and not _expired(entry) for entry in current
        ):
            return False, count
        await _scope(db, row)
        return True, count
    except (AppError, AgentStateError, c.ContractError):
        return False, 0


async def _reserve(
    sessions: async_sessionmaker[AsyncSession],
    *,
    user_id: UUID,
    interview_id: UUID,
    request_id: UUID,
    kind: Literal["auto", "manual"],
    settings: LLMSettings,
    expected_failed_call_id: UUID | None = None,
) -> tuple[dict[str, object], _Scope | None]:
    error: Reason | None = None
    async with sessions.begin() as db:
        try:
            row = await _owned(db, user_id, interview_id)
        except AgentStateError:
            raise AppError(Reason.NOT_FOUND) from None
        ledger = _ledger(row)
        entry = ledger.get(str(request_id))
        if entry is not None:
            if entry.get("kind") != kind:
                raise AppError(Reason.QUESTION_RETRY_UNAVAILABLE)
            # 응답 취소·프로세스 종료가 수동 실패→자동 성공 사이에 생겨도 정확한 자식만 복원한다.
            child_id = str(uuid5(UUID(str(entry["call_id"])), "automatic-rewrite"))
            child = ledger.get(child_id) if kind == "manual" else None
            if child is not None and (
                child.get("kind") == "auto"
                and child.get("failed_call_id") == entry.get("call_id")
                and child.get("target") == entry.get("target")
                and child.get("previous_turn_id") == entry.get("previous_turn_id")
                and child.get("binding") == entry.get("binding")
            ):
                child_call = await db.get(LLMCallRecord, UUID(str(child["call_id"])))
                child_turn = (
                    await db.get(InterviewTurn, child_call.turn_id)
                    if child_call is not None and child_call.turn_id
                    else None
                )
                if (
                    child_call is not None
                    and child_turn is not None
                    and (
                        child_call.interview_session_id == interview_id
                        and child_call.task_name == "director"
                        and child_call.failure is None
                        and child_call.discard_reason is None
                        and child_turn.interview_session_id == interview_id
                        and child_turn.turn_no == entry.get("target")
                    )
                ):
                    child.update(status="succeeded", turn_id=str(child_turn.id))
                    child.setdefault("session_id", secrets.token_urlsafe(32))
                    entry.update(
                        status="succeeded",
                        turn_id=str(child_turn.id),
                        session_id=entry.get("session_id") or child["session_id"],
                        completion="automatic_after_manual",
                    )
                    _store(row, ledger)
                elif child.get("status") == "running" and not _expired(child):
                    raise AppError(Reason.QUESTION_RETRY_IN_PROGRESS)
            # 질문 확정 직후 프로세스가 종료돼도 이미 저장한 성공을 다시 호출하지 않는다.
            call = await db.get(LLMCallRecord, UUID(str(entry["call_id"])))
            if (
                call is not None
                and call.turn_id is not None
                and call.failure is None
                and call.discard_reason is None
            ):
                turn = await db.get(InterviewTurn, call.turn_id)
                if (
                    turn is not None
                    and turn.interview_session_id == row.id
                    and turn.turn_no == entry.get("target")
                ):
                    entry.update(status="succeeded", turn_id=str(turn.id))
                    entry.setdefault("session_id", secrets.token_urlsafe(32))
                    _store(row, ledger)
            if entry.get("status") == "succeeded":
                return entry, None
            if entry.get("status") == "running" and not _expired(entry):
                raise AppError(Reason.QUESTION_RETRY_IN_PROGRESS)
            if entry.get("status") == "running":
                await _expire(db, entry)
                ledger[str(request_id)] = entry
                _store(row, ledger)
            error = Reason.QUESTION_RETRY_FAILED
        else:
            for saved in ledger.values():
                if saved.get("status") == "running":
                    if not _expired(saved):
                        raise AppError(Reason.QUESTION_RETRY_IN_PROGRESS)
                    await _expire(db, saved)
            try:
                scope = await _scope(db, row)
            except (AgentStateError, c.ContractError):
                raise AppError(Reason.QUESTION_RETRY_UNAVAILABLE) from None
            if kind == "auto":
                from devon_ai.agents.director.runtime import recovery_feedback_from_attempts

                failure = scope.failure.failure
                if (
                    scope.failure.id != expected_failed_call_id
                    or failure is None
                    or failure.get("error_code") != "director_candidate_rewrite"
                ):
                    raise AppError(Reason.QUESTION_RETRY_UNAVAILABLE)
                feedback = recovery_feedback_from_attempts(
                    scope.failure.attempts, failure_code="director_candidate_rewrite"
                )
                if feedback is None or feedback.recovery.recovery != "rewrite":
                    raise AppError(Reason.QUESTION_RETRY_UNAVAILABLE)
            if any(
                saved.get("target") == scope.target and saved.get("kind") == kind
                for saved in ledger.values()
            ):
                raise AppError(Reason.QUESTION_RETRY_LIMIT)
            from app.features.interview.director_service import _pending

            try:
                await _pending(db, interview_id, scope.target, "director")
            except AgentStateError:
                raise AppError(Reason.QUESTION_RETRY_IN_PROGRESS) from None
            deadline = datetime.now(UTC) + timedelta(
                seconds=2 * settings.call_limits("director").timeout_seconds + 30
            )
            entry = {
                "request_id": str(request_id),
                "kind": kind,
                "target": scope.target,
                "previous_turn_id": str(scope.previous),
                "failed_call_id": str(scope.failure.id),
                "call_id": str(uuid5(interview_id, "director-question-retry:" + str(request_id))),
                "owner": str(uuid4()),
                "binding": scope.digest,
                "deadline": deadline.isoformat(),
                "status": "running",
            }
            ledger[str(request_id)] = entry
            _store(row, ledger)
            return entry, scope
    assert error is not None
    raise AppError(error)


async def _expire(
    db: AsyncSession, entry: dict[str, object], *, error: str = "execution_expired"
) -> None:
    entry["status"] = "failed"
    entry["error"] = error
    record = await db.get(LLMCallRecord, UUID(str(entry["call_id"])), with_for_update=True)
    if (
        record is not None
        and record.turn_id is None
        and record.failure is None
        and record.discard_reason is None
    ):
        record.discard_reason = "question_retry_expired"


async def _execute(
    sessions: async_sessionmaker[AsyncSession],
    *,
    user_id: UUID,
    interview_id: UUID,
    entry: dict[str, object],
    scope: _Scope,
    settings: LLMSettings,
    http_client: httpx.AsyncClient | None,
) -> QuestionExecution:
    from devon_ai.agents.director.runtime import recovery_feedback_from_attempts

    from app.features.interview.director_service import start_director

    async def guard(db: AsyncSession, row: InterviewSession) -> bool:
        saved = _ledger(row).get(str(entry["request_id"]))
        if saved != entry or saved.get("status") != "running" or _expired(saved):
            return False
        try:
            return (await _scope(db, row)).digest == scope.digest
        except (AppError, AgentStateError, c.ContractError):
            return False

    failure = scope.failure.failure
    assert failure is not None
    code = failure.get("error_code")
    feedback = recovery_feedback_from_attempts(
        scope.failure.attempts, failure_code=code if isinstance(code, str) else ""
    )
    try:
        async with asyncio.timeout(2 * settings.call_limits("director").timeout_seconds + 15):
            outcome = await start_director(
                sessions,
                user_id=user_id,
                interview_id=interview_id,
                call_id=UUID(str(entry["call_id"])),
                settings=settings,
                http_client=http_client,
                answer_analysis=scope.analysis,
                lookup_summary=scope.lookup_summary,
                tool_results=scope.tool_results,
                preparation_guard=guard,
                recovery_feedback=feedback,
            )
    except BaseException as error:
        async with sessions.begin() as db:
            row = await _owned(db, user_id, interview_id)
            ledger = _ledger(row)
            saved = ledger.get(str(entry["request_id"]))
            if (
                saved is not None
                and saved.get("owner") == entry["owner"]
                and saved.get("status") == "running"
            ):
                cause = (
                    "execution_timeout"
                    if isinstance(error, TimeoutError)
                    else "execution_state_changed"
                    if isinstance(error, AgentStateError)
                    else "execution_expired"
                )
                await _expire(db, saved, error=cause)
                _store(row, ledger)
        if isinstance(error, (TimeoutError, AgentStateError)):
            # 실행 중의 예상 가능한 복구 실패도 최초 응답부터 계약상 409로 반환한다.
            # 실제 취소·프로그래밍 오류는 정리 후 원래 예외를 전파한다.
            raise AppError(Reason.QUESTION_RETRY_FAILED) from None
        raise
    async with sessions.begin() as db:
        row = await _owned(db, user_id, interview_id)
        ledger = _ledger(row)
        saved = ledger[str(entry["request_id"])]
        # 동시 재전송이 질문 확정을 먼저 복원했다면 같은 실행의 성공을 만료로 뒤집지 않는다.
        if (
            saved.get("owner") == entry["owner"]
            and saved.get("status") == "succeeded"
            and outcome.turn_id is not None
            and saved.get("turn_id") == str(outcome.turn_id)
        ):
            call = await db.get(LLMCallRecord, outcome.call_id)
            turn = await db.get(InterviewTurn, outcome.turn_id)
            if (
                call is not None
                and call.interview_session_id == interview_id
                and call.task_name == "director"
                and call.turn_id == outcome.turn_id
                and call.failure is None
                and call.discard_reason is None
                and turn is not None
                and turn.interview_session_id == interview_id
                and turn.turn_no == saved.get("target")
            ):
                return outcome
        if saved.get("owner") != entry["owner"] or saved.get("status") != "running":
            return QuestionExecution(outcome.call_id, None, None, "question_retry_expired")
        saved["status"] = "succeeded" if outcome.turn_id is not None else "failed"
        if outcome.turn_id is not None:
            saved["turn_id"] = str(outcome.turn_id)
            saved["session_id"] = secrets.token_urlsafe(32)
        else:
            saved["error"] = (
                outcome.failure.error_code if outcome.failure else outcome.discard_reason
            )
        _store(row, ledger)
    return outcome


async def _run(
    sessions: async_sessionmaker[AsyncSession],
    *,
    user_id: UUID,
    interview_id: UUID,
    entry: dict[str, object],
    scope: _Scope,
    settings: LLMSettings,
    http_client: httpx.AsyncClient | None,
) -> QuestionExecution:
    # HTTP 응답 취소가 이미 시작한 생성 작업을 취소하거나 같은 requestId를 다시 실행하지 않는다.
    task = asyncio.create_task(
        _execute(
            sessions,
            user_id=user_id,
            interview_id=interview_id,
            entry=entry,
            scope=scope,
            settings=settings,
            http_client=http_client,
        )
    )
    _RUNNING.add(task)

    def finished(done: asyncio.Task[QuestionExecution]) -> None:
        _RUNNING.discard(done)
        if not done.cancelled():
            done.exception()

    task.add_done_callback(finished)
    return await asyncio.shield(task)


async def retry_question(
    sessions: async_sessionmaker[AsyncSession],
    redis: Redis,
    *,
    user_id: UUID,
    interview_id: UUID,
    request_id: UUID,
    settings: LLMSettings,
    http_client: httpx.AsyncClient | None = None,
) -> QuestionRetryResponse:
    entry, scope = await _reserve(
        sessions,
        user_id=user_id,
        interview_id=interview_id,
        request_id=request_id,
        kind="manual",
        settings=settings,
    )
    if scope is not None:
        outcome = await _run(
            sessions,
            user_id=user_id,
            interview_id=interview_id,
            entry=entry,
            scope=scope,
            settings=settings,
            http_client=http_client,
        )
        if outcome.turn_id is None:
            # 구버전 실패 뒤 명시 복구가 먼저 온 경우에도 미사용 자동 rewrite 한 번은 허용한다.
            automatic = await auto_retry_question(
                sessions,
                user_id=user_id,
                interview_id=interview_id,
                failed=outcome,
                settings=settings,
                http_client=http_client,
            )
            if automatic is not None and automatic.turn_id is not None:
                async with sessions.begin() as db:
                    row = await _owned(db, user_id, interview_id)
                    ledger = _ledger(row)
                    saved = ledger[str(request_id)]
                    saved.update(
                        status="succeeded",
                        turn_id=str(automatic.turn_id),
                        completion="automatic_after_manual",
                    )
                    saved.setdefault("session_id", secrets.token_urlsafe(32))
                    _store(row, ledger)
                outcome = automatic
        if outcome.turn_id is None:
            raise AppError(Reason.QUESTION_RETRY_FAILED)
    from app.features.interview.service import (
        REALTIME_SESSION_TTL_SECONDS,
        realtime_interview_key,
        realtime_session_key,
    )

    # DB 행 잠금 안에서 현재 미답변 턴과 Redis 회전을 함께 확정한다.
    async with sessions.begin() as db:
        row = await _owned(db, user_id, interview_id)
        entry = _ledger(row)[str(request_id)]
        turn = await db.get(InterviewTurn, UUID(str(entry["turn_id"])))
        target = int(str(entry["target"]))
        if (
            row.status != "in_progress"
            or turn is None
            or turn.interview_session_id != interview_id
            or row.current_turn != target
            or turn.turn_no != target
            or turn.status != "asked"
            or turn.answer_text is not None
        ):
            raise AppError(Reason.QUESTION_RETRY_UNAVAILABLE)
        session_id = str(entry["session_id"])
        try:
            execute = cast(Callable[..., Awaitable[object]], redis.eval)
            await execute(
                _ROTATE,
                1,
                realtime_interview_key(interview_id),
                session_id,
                json.dumps({"interviewId": str(interview_id), "userId": str(user_id)}),
                REALTIME_SESSION_TTL_SECONDS,
                realtime_session_key(""),
            )
        except RedisError:
            raise AppError(Reason.INTERNAL_ERROR) from None
    return QuestionRetryResponse(interview_id=interview_id, session_id=session_id, turn_no=target)
