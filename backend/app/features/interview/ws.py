"""저장된 질문을 복구하고 단일 연결에서 답변 분석·Director를 실행한다."""

import asyncio
import json
import re
import secrets
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from math import isfinite
from typing import Any, cast
from uuid import UUID, uuid4

from anyio import CancelScope
from devon_ai import contracts as c
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError
from redis.asyncio import Redis
from redis.asyncio.client import PubSub
from redis.exceptions import RedisError
from sqlalchemy import select
from starlette.responses import JSONResponse

from app.agents.director.tools import EvidenceLimits
from app.core.config import INTERVIEW_MAX_TURNS, LLMSettings, Settings
from app.core.deps import current_user
from app.core.errors import AppError
from app.core.logging import get_logger
from app.db.models import InterviewSession, LLMCallRecord, Repository
from app.features.interview.agent_context import AgentStateError
from app.features.interview.answer_audio import (
    AUDIO_TOO_LONG_CAUSE,
    AnswerAudioBuffer,
    AnswerAudioLimits,
    AnswerAudioTooLong,
    AnswerEnd,
    AnswerStart,
    NoActiveAnswer,
    parse_voice_message,
    turn_rejection,
)
from app.features.interview.director_service import AnswerExecution, log_recovery, process_answer
from app.features.interview.queries import list_turns
from app.features.interview.question_audio import question_audio_url
from app.features.interview.question_replay import ExplicitReplayCommands, should_replay
from app.features.interview.schemas import InterviewLastError
from app.features.interview.service import (
    REALTIME_SESSION_TTL_SECONDS,
    expire_if_due,
    realtime_interview_key,
    realtime_session_key,
)
from app.features.interview.turn_position import turn_position
from app.integrations.stt.client import MlapiSttClient, SttError, SttFailureCause
from app.shared.enums import PrepareStepKey, Reason

router = APIRouter(prefix="/ws/interviews", tags=["interview"])
logger = get_logger(__name__)
_SESSION_ID = re.compile(r"[A-Za-z0-9_-]{43}")
_LEASE_SECONDS = 30
_WORK_HEARTBEAT_SECONDS = _LEASE_SECONDS / 3
_WORK_LOCAL_SECONDS = 30
_WORK_CLEANUP_SECONDS = 30
_WORK_TASKS: set[asyncio.Task[AnswerExecution]] = set()
_PREPARE_POLL_SECONDS = 1.0
_REFRESH = """
if redis.call('GET', KEYS[1]) ~= ARGV[1]
or redis.call('GET', KEYS[2]) ~= ARGV[2]
or redis.call('GET', KEYS[3]) ~= ARGV[3] then return 0 end
redis.call('EXPIRE', KEYS[1], ARGV[4])
redis.call('EXPIRE', KEYS[2], ARGV[5])
redis.call('EXPIRE', KEYS[3], ARGV[5])
return 1
"""
_RELEASE = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
return redis.call('DEL', KEYS[1]) end
return 0
"""
_CACHE = """
if redis.call('GET', KEYS[1]) ~= ARGV[1] then return 0 end
redis.call('SET', KEYS[2], ARGV[2], 'EX', ARGV[3])
return 1
"""
_BEGIN_WORK = """
if redis.call('GET', KEYS[1]) ~= ARGV[1]
or redis.call('GET', KEYS[3]) ~= ARGV[2]
or redis.call('GET', KEYS[4]) ~= ARGV[3] then return 0 end
if redis.call('SET', KEYS[2], ARGV[1], 'NX', 'EX', ARGV[4]) then return 1 end
return 0
"""
_REFRESH_WORK = """
if redis.call('GET', KEYS[1]) ~= ARGV[1] then return 0 end
return redis.call('EXPIRE', KEYS[1], ARGV[2])
"""


def _answer_work_seconds(config: Settings, llm: LLMSettings) -> float:
    # T3는 두 시도와 최대 한 번의 Retry-After 대기, T4는 최초·자동 rewrite 각각
    # plan/review 두 호출이다. 외부 조회는 실제 설정된 전체 호출 상한을 공유한다.
    # DB·콜백 등 로컬 작업에는 전체 실행 deadline 안에서 별도 30초만 허용한다.
    external_calls = min(config.tavily_max_calls, config.external_max_calls_per_interview)
    seconds = (
        3 * llm.call_limits("answer_analysis").timeout_seconds
        + 4 * llm.call_limits("director").timeout_seconds
        + config.director_evidence_timeout_seconds
        + external_calls * config.tavily_timeout_seconds
        + _WORK_LOCAL_SECONDS
    )
    if not isfinite(seconds):
        raise AgentStateError("answer_work_budget_invalid")
    return seconds


def _work_finished(task: asyncio.Task[AnswerExecution]) -> None:
    # DB 정리가 기한을 넘겨도 작업을 보존하고 뒤늦은 예외를 반드시 회수한다.
    _WORK_TASKS.discard(task)
    if not task.cancelled():
        task.exception()


@dataclass(frozen=True)
class _State:
    status: str
    question: dict[str, object] | None
    snapshot: dict[str, object]
    last_error: dict[str, object] | None
    prepare_steps: tuple[tuple[str, str], ...]
    answer_mode: str = "voice"


def _preparation_steps(raw: object) -> tuple[tuple[str, str], ...]:
    """저장된 네 단계만 공개 이벤트로 내보내며 임의 상태를 만들지 않는다."""
    if type(raw) is not list or len(raw) > 4:
        raise AgentStateError("prepare_steps_invalid")
    steps: dict[str, str] = {}
    for item in raw:
        if type(item) is not dict:
            raise AgentStateError("prepare_steps_invalid")
        key, status = item.get("step"), item.get("status")
        if (
            type(key) is not str
            or key not in PrepareStepKey
            or key in steps
            or type(status) is not str
            or status not in {"pending", "running", "completed", "failed"}
        ):
            raise AgentStateError("prepare_steps_invalid")
        steps[key] = status
    return tuple(steps.items())


async def _script(redis: Redis, script: str, key_count: int, *values: object) -> object:
    # 설치된 redis stubs의 sync/async 공통 명령 표기를 비동기 클라이언트 경계에서 좁힌다.
    execute = cast(Callable[..., Awaitable[object]], redis.execute_command)
    return await execute("EVAL", script, key_count, *values)


def _error(
    reason: str,
    *,
    step: str | None = None,
    recoverable: bool = True,
    details: dict[str, object] | None = None,
) -> dict[str, object]:
    event: dict[str, object] = {
        "type": "error",
        "reason": reason,
        "recoverable": recoverable,
        "code": "ERR_" + reason.upper(),
        "step": step,
        "occurredAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }
    # details가 없으면 기존 error JSON과 키까지 같아야 한다.
    if details is not None:
        event["details"] = details
    return event


# 다시 답변해도 복구되지 않는 STT 실패(설정 누락·인증 오류). FE가 반복 안내 대신 서비스 불가로 본다.
_STT_UNAVAILABLE: dict[str, Any] = {
    "recoverable": False,
    "details": {"cause": "stt_unavailable"},
}


async def _deny(socket: WebSocket, reason: str, status: int = 409) -> None:
    response = JSONResponse(
        {
            "error": {
                "reason": reason,
                "message": "면접 연결을 확인해 주세요.",
                "details": {},
            }
        },
        status_code=status,
    )
    if "websocket.http.response" in socket.scope.get("extensions", {}):
        await socket.send_denial_response(response)
    else:
        await socket.close(code=1008, reason=reason)


async def _authenticated_user(socket: WebSocket) -> UUID:
    # yield dependency를 WS 수명에 묶지 않아 모델 응답을 기다리는 동안 DB 읽기를 유지하지 않는다.
    async with socket.app.state.session_factory() as db:
        user = await current_user(socket, db)
        return user.id


async def _read_state(socket: WebSocket, user_id: UUID, interview_id: UUID) -> _State:
    async with socket.app.state.session_factory() as db:
        interview = await db.get(InterviewSession, interview_id)
        if interview is None or interview.user_id != user_id:
            raise AppError(Reason.NOT_FOUND)
        # 준비 중 폴링은 세션 한 행만 읽는다. 질문·pending 조회는 준비 완료 뒤에 한다.
        turns = (
            []
            if interview.status == "preparing"
            else await list_turns(db, interview_id=interview_id)
        )
        pending = (
            None
            if interview.status != "in_progress"
            else await db.scalar(
                select(LLMCallRecord.id)
                .where(
                    LLMCallRecord.interview_session_id == interview_id,
                    LLMCallRecord.turn_no >= interview.current_turn,
                    LLMCallRecord.turn_id.is_(None),
                    LLMCallRecord.failure.is_(None),
                    LLMCallRecord.discard_reason.is_(None),
                )
                .limit(1)
            )
        )
        current = next((turn for turn in turns if turn.turn_no == interview.current_turn), None)
        question = None
        if (
            interview.status == "in_progress"
            and current is not None
            and current.status == "asked"
            and current.answer_text is None
            and pending is None
        ):
            main_index, follow_up_depth = turn_position(
                [(turn.turn_no, turn.depth, turn.parent_turn_no) for turn in turns], current.turn_no
            )
            question = {
                "type": "question",
                "persona": current.persona,
                "text": current.question_text,
                "turn": current.turn_no,
                "mainIndex": main_index,
                "followUpDepth": follow_up_depth,
                # 텍스트를 즉시 전달하고 음성은 인증된 별도 요청에서 합성·캐시한다.
                "audioUrl": question_audio_url(
                    socket.app.state.settings.api_prefix, interview_id, current.turn_no
                )
                if interview.answer_mode == "voice"
                and getattr(socket.app.state.settings, "tts_provider", None)
                else None,
            }
        snapshot = {
            "status": interview.status,
            "currentTurn": interview.current_turn,
            "totalTurns": interview.total_turns,
            "context": interview.context_state,
            "turns": [
                {
                    "turn": turn.turn_no,
                    "persona": turn.persona,
                    "question": turn.question_text,
                    "answer": turn.answer_text,
                }
                for turn in turns
            ],
        }
        return _State(
            interview.status,
            question,
            snapshot,
            interview.last_error,
            _preparation_steps(interview.prepare_steps),
            interview.answer_mode,
        )


async def _expire(socket: WebSocket, user_id: UUID, interview_id: UUID) -> bool:
    """답변 대기 중 제한 시간이 다 됐으면 면접을 completed 로 끝낸다 (#246)."""
    async with socket.app.state.session_factory() as db:
        interview = await db.get(InterviewSession, interview_id)
        if interview is None or interview.user_id != user_id:
            return False
        return await expire_if_due(db, interview)


class _Connection:
    def __init__(
        self,
        socket: WebSocket,
        redis: Redis,
        session_id: str,
        interview_id: UUID,
        raw_session: bytes | str,
        nonce: str,
    ) -> None:
        self.socket, self.redis = socket, redis
        self.session_id, self.interview_id = session_id, interview_id
        self.raw_session, self.nonce = raw_session, nonce
        self.lock = f"ws:lock:{session_id}"
        self.work = f"ws:work:{session_id}"
        self.connected = True
        self.closed = asyncio.Event()
        self.outgoing = asyncio.Lock()
        # 수신 task는 타임아웃·호출 취소로 버리지 않고 다음 receive가 이어받아 프레임을 잃지 않는다.
        self._incoming: asyncio.Task[object] | None = None

    async def acquire(self) -> bool:
        # 프로세스가 달라도 이전 소켓을 먼저 닫는다. 잠금 값을 강제로 덮어쓰지 않는다.
        try:
            async with asyncio.timeout(_LEASE_SECONDS + 1):
                while not await self.redis.set(self.lock, self.nonce, ex=_LEASE_SECONDS, nx=True):
                    owner = await self.redis.get(self.lock)
                    if owner is not None:
                        await self.redis.publish(f"ws:replace:{self.session_id}", owner)
                    # 구독 시작 경합이나 알림 유실은 다음 획득 시도에서 다시 알린다.
                    await asyncio.sleep(0.05)
            return True
        except TimeoutError:
            return False

    async def watch_replacement(self, control: PubSub) -> None:
        try:
            async for message in control.listen():
                if message["type"] == "message" and message["data"] in (
                    self.nonce,
                    self.nonce.encode(),
                ):
                    await self.close()
                    return
        except RedisError:
            await self.close(1011)

    async def send(self, event: dict[str, object]) -> None:
        async with self.outgoing:
            if not self.connected:
                return
            try:
                if await self.refresh():
                    await self.socket.send_json(event)
                    return
            except (RedisError, WebSocketDisconnect, OSError, RuntimeError):
                pass
        # 전송 실패는 이미 확정한 답변·실행 중 분석을 되돌리지 않는다.
        await self.close()

    async def close(self, code: int = 1000) -> None:
        async with self.outgoing:
            if self.connected:
                with suppress(WebSocketDisconnect, OSError, RuntimeError):
                    await self.socket.close(code=code)
                # 종료 대기 중인 restore가 먼저 반환해 이 close 작업을 취소하면 안 된다.
                self.connected = False
            # 실제 소켓 종료 뒤 해제한다. 오래된 정리 작업은 새 소유자의 잠금을 지울 수 없다.
            with CancelScope(shield=True), suppress(RedisError):
                await _script(self.redis, _RELEASE, 1, self.lock, self.nonce)
            self.closed.set()

    async def _read_frame(self) -> object:
        """text 프레임은 JSON으로, binary 프레임은 bytes로 돌려준다."""
        message = await self.socket.receive()
        if message["type"] == "websocket.disconnect":
            raise WebSocketDisconnect(message.get("code", 1000))
        if message.get("bytes") is not None:
            return cast(bytes, message["bytes"])
        text = message.get("text")
        if text is None:
            raise ValueError("empty websocket frame")
        return json.loads(text)

    async def receive(self, wait_seconds: float | None = None) -> object:
        """다음 프레임을 기다린다. wait_seconds 안에 없으면 TimeoutError이고 프레임은 유지된다."""
        if self._incoming is None:
            self._incoming = asyncio.create_task(self._read_frame())
        closing = asyncio.create_task(self.closed.wait())
        try:
            await asyncio.wait(
                (self._incoming, closing), timeout=wait_seconds, return_when=asyncio.FIRST_COMPLETED
            )
            if closing.done():
                raise WebSocketDisconnect()
            if not self._incoming.done():
                raise TimeoutError
            incoming, self._incoming = self._incoming, None
            return incoming.result()
        finally:
            closing.cancel()
            with CancelScope(shield=True):
                await asyncio.gather(closing, return_exceptions=True)

    async def release_receiver(self) -> None:
        incoming, self._incoming = self._incoming, None
        if incoming is not None:
            incoming.cancel()
            with CancelScope(shield=True):
                await asyncio.gather(incoming, return_exceptions=True)

    async def refresh(self) -> bool:
        return bool(
            await _script(
                self.redis,
                _REFRESH,
                3,
                self.lock,
                realtime_session_key(self.session_id),
                realtime_interview_key(self.interview_id),
                self.nonce,
                self.raw_session,
                self.session_id,
                _LEASE_SECONDS,
                REALTIME_SESSION_TTL_SECONDS,
            )
        )

    async def heartbeat(self) -> None:
        while self.connected:
            await asyncio.sleep(_LEASE_SECONDS / 3)
            try:
                valid = await self.refresh()
            except RedisError:
                valid = False
            if not valid:
                await self.close(1011)

    async def work_heartbeat(self) -> None:
        # 소켓·로그인 세션이 교체돼도 이미 접수한 작업은 자기 nonce로만 갱신한다.
        while True:
            await asyncio.sleep(_WORK_HEARTBEAT_SECONDS)
            try:
                valid = await _script(
                    self.redis, _REFRESH_WORK, 1, self.work, self.nonce, _LEASE_SECONDS
                )
            except RedisError:
                valid = False
            if not valid:
                raise AgentStateError("answer_work_ownership_lost")

    async def preparation(self, state: _State, user_id: UUID) -> _State:
        """DB 스냅샷과 변경분을 복원하며 재연결로 준비 작업을 재실행하지 않는다."""
        observed: dict[str, str] = {}
        receiving = asyncio.create_task(self.receive())
        try:
            while self.connected:
                for key, status in state.prepare_steps:
                    if observed.get(key) != status:
                        await self.send({"type": "prepareStep", "key": key, "status": status})
                        observed[key] = status
                if state.status != "preparing":
                    break
                deadline = asyncio.get_running_loop().time() + _PREPARE_POLL_SECONDS
                while self.connected:
                    remaining = deadline - asyncio.get_running_loop().time()
                    if remaining <= 0:
                        break
                    done, _ = await asyncio.wait((receiving,), timeout=remaining)
                    if not done:
                        break
                    try:
                        receiving.result()
                    except (ValueError, KeyError):
                        pass
                    # 수신 task를 조회 주기마다 취소하지 않아 이미 받은 프레임을 잃지 않는다.
                    await self.send(_error("answer_rejected"))
                    receiving = asyncio.create_task(self.receive())
                if self.connected:
                    state = await _read_state(self.socket, user_id, self.interview_id)
        finally:
            receiving.cancel()
            with CancelScope(shield=True):
                await asyncio.gather(receiving, return_exceptions=True)
        return state

    async def restore(self, user_id: UUID) -> bool:
        # 교체된 소켓이 확정한 답변의 T3→Tool→T4가 끝날 때까지 기다릴 뿐 재실행하지 않는다.
        # T3 저장과 T4 시작 사이에는 DB pending 기록이 잠시 없을 수도 있다.
        while self.connected and await self.redis.exists(self.work):
            with suppress(TimeoutError):
                await asyncio.wait_for(self.closed.wait(), timeout=0.05)
        if not self.connected:
            return False
        state = await _read_state(self.socket, user_id, self.interview_id)
        if state.status == "abandoned":
            # 중단 알림이 유실돼도 DB의 확정 상태에서 과거 질문을 다시 전달하지 않는다.
            await self.close()
            return False
        preparing = state.status == "preparing"
        if preparing:
            state = await self.preparation(state, user_id)
            if not self.connected:
                return False
        saved = await _script(
            self.redis,
            _CACHE,
            2,
            self.lock,
            f"iv:ctx:{self.interview_id}",
            self.nonce,
            json.dumps(state.snapshot, ensure_ascii=False),
            REALTIME_SESSION_TTL_SECONDS,
        )
        if not saved:
            await self.close()
            return False
        if state.status == "completed":
            await self.send({"type": "interviewEnd"})
            await self.close()
            return False
        if state.question is not None:
            if preparing:
                await self.send({"type": "prepareCompleted"})
            await self.send(state.question)
            return self.connected
        # 진행 중 면접은 재접속해도 실패한 분석·질문 생성을 다시 실행하지 않는다. 복구할 수
        # 없는 실패이므로 FE가 재연결을 멈추고 abandon 후 새 면접으로 안내하게 한다(공통 0010).
        event = _error("question_failed", recoverable=state.status != "in_progress")
        if state.status == "preparing_failed" and state.last_error:
            try:
                last = InterviewLastError.model_validate(state.last_error)
                event = {"type": "error", **last.model_dump(mode="json", by_alias=True)}
            except ValueError:
                pass
        await self.send(event)
        await self.close()
        return False

    async def answer_saved(self) -> None:
        await self.send({"type": "answerReceived"})
        await self.send({"type": "thinking"})

    async def evidence_checked(self, items: tuple[c.Evidence, ...]) -> None:
        # service는 유효 근거 commit 뒤에만 이 콜백을 실행한다.
        events: list[dict[str, object]] = []
        async with self.socket.app.state.session_factory() as db:
            for item in items:
                if item.repository_id is None:
                    continue
                repo = await db.get(Repository, UUID(item.repository_id))
                if repo is not None:
                    events.append(
                        {
                            "type": "evidenceCheck",
                            "repository": repo.name,
                            "file": item.path or item.metadata_key or "",
                        }
                    )
        for event in events:
            await self.send(event)


def _answer(raw: object) -> tuple[int, str] | str:
    if (
        type(raw) is not dict
        or set(raw) != {"type", "turn", "text"}
        or raw.get("type") != "answer"
        or type(raw.get("turn")) is not int
        or not 1 <= raw["turn"] <= INTERVIEW_MAX_TURNS
        or type(raw.get("text")) is not str
        or not raw["text"].strip()
        or any(0xD800 <= ord(char) <= 0xDFFF for char in raw["text"])
    ):
        return "answer_rejected"
    if len(raw["text"]) > 2000:
        return "answer_too_long"
    return raw["turn"], raw["text"]


def _answer_audio_buffer(socket: WebSocket) -> AnswerAudioBuffer:
    config = socket.app.state.settings
    return AnswerAudioBuffer(
        AnswerAudioLimits(
            max_bytes=config.stt_max_audio_bytes,
            max_seconds=config.answer_audio_max_seconds,
            grace_seconds=config.answer_audio_grace_seconds,
            idle_timeout_seconds=config.answer_audio_idle_timeout_seconds,
        )
    )


async def _answer_start(
    connection: _Connection, user_id: UUID, buffer: AnswerAudioBuffer, start: AnswerStart
) -> None:
    """지금 답변할 수 있는 턴일 때만 새 오디오를 받기 시작한다. 거절해도 받던 오디오는 둔다."""
    state = await _read_state(connection.socket, user_id, connection.interview_id)
    if state.status != "in_progress" or state.answer_mode != "voice":
        await connection.send(_error("answer_rejected"))
        return
    current_turn = cast(int, state.snapshot["currentTurn"])
    answerable = cast(int, state.question["turn"]) if state.question is not None else None
    reason = turn_rejection(start.turn, current_turn, answerable)
    if reason is not None:
        await connection.send(_error(reason))
        return
    buffer.start(start.turn, start.mime_type)


async def _answer_chunk(connection: _Connection, buffer: AnswerAudioBuffer, chunk: bytes) -> None:
    turn = buffer.active_turn
    try:
        buffer.append(chunk)
    except AnswerAudioTooLong:
        await _audio_too_long(connection, turn)


async def _audio_too_long(connection: _Connection, turn: int | None) -> None:
    logger.warning("answer_audio_too_long", interview_id=str(connection.interview_id), turn=turn)
    limit = connection.socket.app.state.settings.answer_audio_max_seconds
    await connection.send(
        _error(
            "answer_too_long",
            details={"cause": AUDIO_TOO_LONG_CAUSE, "limitSeconds": int(limit)},
        )
    )


def _stt_client(socket: WebSocket) -> MlapiSttClient:
    state = socket.app.state
    # 테스트는 app.state.stt_client로 mock 전사기를 주입한다. 없으면 설정을 호출 시점에 검증한다.
    injected = getattr(state, "stt_client", None)
    return injected if injected is not None else MlapiSttClient(state.settings.require_stt())


async def _answer_end(
    connection: _Connection, user_id: UUID, buffer: AnswerAudioBuffer, end: AnswerEnd
) -> bool:
    """받은 오디오를 전사해 `transcript`를 보낸 뒤 기존 처리 경로로 저장·진행한다.

    순서는 transcript → answerReceived → thinking 이다(FE mock 기준). transcript는 저장 전에 보낸다.
    """
    try:
        audio = buffer.end(end.turn)
    except NoActiveAnswer:
        await connection.send(_error("answer_rejected"))
        return True
    except AnswerAudioTooLong:
        await _audio_too_long(connection, end.turn)
        return True
    current = await _read_state(connection.socket, user_id, connection.interview_id)
    if (
        current.status != "in_progress"
        or current.answer_mode != "voice"
        or current.question is None
        or current.question["turn"] != end.turn
    ):
        # 녹음 도중 중단·턴 확정·입력 모드 변경이 일어나면 유료 전사를 시작하지 않는다.
        await connection.send(_error("answer_rejected"))
        return True
    try:
        text = await _stt_client(connection.socket).transcribe(audio.data, audio.mime_type)
    except SttError as exc:
        # 공급자 원문·상태 코드는 어디에도 싣지 않는다. 빈 전사만 FE가 구분하도록 cause를 보낸다.
        logger.warning(
            "interview_ws_stt_failed",
            interview_id=str(connection.interview_id),
            turn=end.turn,
            exception_type=type(exc).__name__,
        )
        if exc.cause is SttFailureCause.EMPTY_TRANSCRIPT:
            await connection.send(_error("stt_failed", details={"cause": "empty_transcript"}))
        elif exc.cause is SttFailureCause.UNAUTHORIZED:
            # 키 문제는 다시 답변해도 풀리지 않는다.
            await connection.send(_error("stt_failed", **_STT_UNAVAILABLE))
        else:
            await connection.send(_error("stt_failed"))
        return True
    except ValueError as exc:
        # 설정 누락·오류. 값(주소·키)은 남기지 않는다.
        logger.error(
            "interview_ws_stt_configuration_invalid",
            interview_id=str(connection.interview_id),
            turn=end.turn,
            exception_type=type(exc).__name__,
        )
        await connection.send(_error("stt_failed", **_STT_UNAVAILABLE))
        return True
    await connection.send({"type": "transcript", "turn": end.turn, "text": text})
    return await _run_answer(connection, user_id, end.turn, text, "answer_rejected")


async def _run_answer(
    connection: _Connection,
    user_id: UUID,
    turn: int,
    text: str,
    invalid_turn_reason: str,
    *,
    answer_mode: str = "voice",
) -> bool:
    """저장·분석·다음 질문 복구까지 수행한다. 연결을 더 쓸 수 없으면 False."""
    classifier = getattr(connection.socket.app.state, "replay_intent_classifier", None)
    if answer_mode == "voice" and (
        ExplicitReplayCommands().is_explicit(text) or classifier is not None
    ):
        current = await _read_state(connection.socket, user_id, connection.interview_id)
        question = current.question
        if current.answer_mode == "voice" and question is not None and question["turn"] == turn:
            if await should_replay(text, str(question["text"]), classifier):
                # 분류 대기 중 다른 턴이 확정됐으면 오래된 질문을 다시 전달하지 않는다.
                latest = await _read_state(connection.socket, user_id, connection.interview_id)
                if latest.question is not None and latest.question == question:
                    await connection.send(latest.question)
                    return True
    try:
        result = await _execute(connection, user_id, turn, text, answer_mode=answer_mode)
    except AgentStateError as exc:
        if exc.reason == "time_up":
            # 시간이 다 된 뒤의 답변은 저장하지 않는다. restore 가 interviewEnd 를 보낸다(#246).
            await connection.restore(user_id)
            return False
        if exc.reason == "answer_turn_invalid":
            # 저장되지 않았으므로 answerReceived는 가지 않았다. 텍스트는 stale, 음성은 rejected.
            await connection.send(_error(invalid_turn_reason))
            return True
        # 다른 연결이 작업 중이거나 이 연결이 교체된 경우만 재접속으로 풀린다.
        recoverable = exc.reason == "connection_replaced_or_busy"
        await connection.send(_error("question_failed", recoverable=recoverable))
        await connection.close()
        return False
    if result.failure is not None or result.discard_reason is not None:
        log_recovery(result.failure, "turn")
        await connection.send(_error("question_failed", recoverable=False))
        await connection.close()
        return False
    return await connection.restore(user_id)


async def _execute(
    connection: _Connection, user_id: UUID, turn: int, text: str, *, answer_mode: str
) -> AnswerExecution:
    if await _expire(connection.socket, user_id, connection.interview_id):
        raise AgentStateError("time_up")
    state = connection.socket.app.state
    config = state.settings
    current = await _read_state(connection.socket, user_id, connection.interview_id)
    if (
        current.status != "in_progress"
        or current.answer_mode != answer_mode
        or current.question is None
        or current.question["turn"] != turn
    ):
        raise AgentStateError("answer_turn_invalid")
    try:
        llm = config.require_llm()
    except ValidationError as error:
        # 설정 값·키 원문 없이 필드 이름만 남겨 사용자 답변 오류와 구분한다.
        fields = sorted({str(item["loc"][0]) for item in error.errors() if item["loc"]})
        logger.error(
            "interview_ws_llm_configuration_invalid",
            interview_id=str(connection.interview_id),
            fields=fields,
        )
        raise
    except ValueError:
        # require_llm의 proxy 쌍 불일치만 분류하며 외부 실행 오류를 포괄하지 않는다.
        logger.error(
            "interview_ws_llm_configuration_invalid",
            interview_id=str(connection.interview_id),
            fields=["proxy_token", "chat_proxy_url"],
        )
        raise
    # WS 전송 수명 취소가 이미 시작한 DB·모델 처리를 중단하지 않게 한다.
    lifetime = _answer_work_seconds(config, llm)
    with CancelScope(shield=True):
        claimed = await _script(
            connection.redis,
            _BEGIN_WORK,
            4,
            connection.lock,
            connection.work,
            realtime_session_key(connection.session_id),
            realtime_interview_key(connection.interview_id),
            connection.nonce,
            connection.raw_session,
            connection.session_id,
            _LEASE_SECONDS,
        )
        if not claimed:
            raise AgentStateError("connection_replaced_or_busy")
        processing = asyncio.create_task(
            process_answer(
                state.session_factory,
                user_id=user_id,
                interview_id=connection.interview_id,
                turn_no=turn,
                text=text,
                call_id=uuid4(),
                settings=llm,
                external_settings=config,
                http_client=state.http_client,
                evidence_limits=EvidenceLimits(
                    config.director_evidence_max_requests,
                    config.director_evidence_max_files,
                    config.director_evidence_max_response_bytes,
                    config.director_evidence_max_total_bytes,
                    config.director_evidence_timeout_seconds,
                ),
                on_answer_saved=connection.answer_saved,
                on_evidence_check=connection.evidence_checked,
            )
        )
        _WORK_TASKS.add(processing)
        processing.add_done_callback(_work_finished)
        heartbeat = asyncio.create_task(connection.work_heartbeat())
        try:
            async with asyncio.timeout(lifetime):
                done, _ = await asyncio.wait(
                    (processing, heartbeat), return_when=asyncio.FIRST_COMPLETED
                )
                if heartbeat in done:
                    heartbeat.result()
                result = await processing
        except TimeoutError:
            raise AgentStateError("answer_execution_timeout") from None
        finally:
            # 취소된 모델·자동 rewrite의 DB claim과 외부 조회 예약 정리를 먼저 합류한다.
            # 정리 중에도 heartbeat를 유지하고, 새 작업 소유자의 표식은 건드리지 않는다.
            async def finish() -> None:
                processing.cancel()
                try:
                    done, _ = await asyncio.wait((processing,), timeout=_WORK_CLEANUP_SECONDS)
                    if not done:
                        processing.cancel()
                        # DB 정리가 끝났다고 간주하지 않는다. 갱신을 멈추고 유한 lease로 만료한다.
                        raise AgentStateError("answer_work_cleanup_timeout")
                finally:
                    heartbeat.cancel()
                    await asyncio.gather(heartbeat, return_exceptions=True)
                with suppress(RedisError):
                    await _script(connection.redis, _RELEASE, 1, connection.work, connection.nonce)

            cleanup = asyncio.create_task(finish())
            canceled = False
            while True:
                try:
                    # asyncio의 반복 취소도 정리 작업에는 전달하지 않고 완료 뒤 전파한다.
                    await asyncio.shield(cleanup)
                    break
                except asyncio.CancelledError:
                    if cleanup.cancelled():
                        raise
                    canceled = True
            if canceled:
                raise asyncio.CancelledError
    return result


async def _handle_input(
    connection: _Connection,
    user_id: UUID,
    audio: AnswerAudioBuffer,
    raw_answer: object,
    answer_mode: str,
) -> bool:
    """세션의 고정 입력 모드를 전사·평가·저장 전에 검사한다."""
    if isinstance(raw_answer, bytes):
        if answer_mode != "voice":
            await connection.send(_error("answer_rejected"))
            return True
        await _answer_chunk(connection, audio, raw_answer)
        return True
    voice = parse_voice_message(raw_answer)
    if isinstance(voice, (AnswerStart, AnswerEnd)):
        if answer_mode != "voice":
            await connection.send(_error("answer_rejected"))
            return True
        if isinstance(voice, AnswerStart):
            await _answer_start(connection, user_id, audio, voice)
            return True
        return await _answer_end(connection, user_id, audio, voice)
    if answer_mode != "text":
        await connection.send(_error("answer_rejected"))
        return True
    parsed = _answer(raw_answer)
    if isinstance(parsed, str):
        await connection.send(_error(parsed))
        return True
    turn, text = parsed
    return await _run_answer(
        connection, user_id, turn, text, "answer_stale_turn", answer_mode=answer_mode
    )


@router.websocket("/{session_id}")
async def interview_socket(socket: WebSocket, session_id: str) -> None:
    user_id = await _authenticated_user(socket)
    if not _SESSION_ID.fullmatch(session_id):
        await _deny(socket, "session_expired")
        return
    redis: Redis = socket.app.state.redis
    raw = await redis.get(realtime_session_key(session_id))
    try:
        data = json.loads(raw) if raw is not None else None
        if (
            type(data) is not dict
            or set(data) != {"interviewId", "userId"}
            or type(data["interviewId"]) is not str
            or type(data["userId"]) is not str
            or UUID(data["userId"]) != user_id
        ):
            raise ValueError
        interview_id = UUID(data["interviewId"])
    except (ValueError, TypeError, UnicodeDecodeError):
        await _deny(socket, "session_expired")
        return
    await _expire(socket, user_id, interview_id)
    initial = await _read_state(socket, user_id, interview_id)
    if initial.status in {"completed", "abandoned"}:
        await _deny(socket, "session_expired")
        return
    nonce = secrets.token_urlsafe(32)
    assert raw is not None
    connection = _Connection(socket, redis, session_id, interview_id, raw, nonce)
    audio = _answer_audio_buffer(socket)
    heartbeat = watcher = None
    control = redis.pubsub()
    try:
        await control.subscribe(f"ws:replace:{session_id}")
        if not await connection.acquire():
            await _deny(socket, "already_connected")
            return
        if not await connection.refresh():
            await _deny(socket, "session_expired")
            return
        # 인계를 기다리는 사이 이전 실행이 면접을 끝냈을 수 있다.
        if (await _read_state(socket, user_id, interview_id)).status in {"completed", "abandoned"}:
            await _deny(socket, "session_expired")
            return
        if not await connection.refresh():
            await _deny(socket, "session_expired")
            return
        await socket.accept()
        watcher = asyncio.create_task(connection.watch_replacement(control))
        heartbeat = asyncio.create_task(connection.heartbeat())
        if not await connection.restore(user_id):
            return
        while connection.connected:
            try:
                raw_answer = await connection.receive(audio.idle_remaining())
            except TimeoutError:
                # 오디오가 오지 않으면 미완료 오디오를 버린다. 클라이언트에는 알리지 않는다(0007).
                audio.discard_if_idle()
                continue
            except (ValueError, KeyError):
                await connection.send(_error("answer_rejected"))
                continue
            # 로그인 인증은 handshake에서 확정한다. 답변에서는 면접 연결 소유권만 확인한다.
            if not await connection.refresh():
                await connection.close(1008)
                return
            if not await _handle_input(connection, user_id, audio, raw_answer, initial.answer_mode):
                return
    except WebSocketDisconnect:
        connection.connected = False
    except Exception as exc:
        logger.error("interview_ws_failed", exception_type=type(exc).__name__)
        await connection.send(_error("question_failed"))
        await connection.close(1011)
    finally:
        # 연결이 끝나면 미완료 오디오를 버린다. 재연결 뒤에는 같은 턴을 다시 답변한다(0007).
        audio.discard()
        await connection.release_receiver()
        for task in (heartbeat, watcher):
            if task is not None:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
        with CancelScope(shield=True), suppress(RedisError):
            await _script(redis, _RELEASE, 1, connection.lock, nonce)
        with CancelScope(shield=True), suppress(RedisError):
            await cast(Callable[[], Awaitable[None]], control.aclose)()
