"""저장된 질문을 복구하고 단일 연결에서 답변 분석·Director를 실행한다."""

import asyncio
import json
import re
import secrets
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from math import ceil
from typing import cast
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
from app.core.config import INTERVIEW_MAX_TURNS
from app.core.deps import current_user
from app.core.errors import AppError
from app.core.logging import get_logger
from app.db.models import InterviewSession, LLMCallRecord, Repository
from app.features.interview.agent_context import AgentStateError
from app.features.interview.director_service import AnswerExecution, process_answer
from app.features.interview.queries import list_turns
from app.features.interview.schemas import InterviewLastError
from app.features.interview.service import (
    REALTIME_SESSION_TTL_SECONDS,
    realtime_interview_key,
    realtime_session_key,
)
from app.shared.enums import PrepareStepKey, Reason

router = APIRouter(prefix="/ws/interviews", tags=["interview"])
logger = get_logger(__name__)
_SESSION_ID = re.compile(r"[A-Za-z0-9_-]{43}")
_LEASE_SECONDS = 30
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


@dataclass(frozen=True)
class _State:
    status: str
    question: dict[str, object] | None
    snapshot: dict[str, object]
    last_error: dict[str, object] | None
    prepare_steps: tuple[tuple[str, str], ...]


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


def _error(reason: str, *, step: str | None = None) -> dict[str, object]:
    return {
        "type": "error",
        "reason": reason,
        "recoverable": True,
        "code": "ERR_" + reason.upper(),
        "step": step,
        "occurredAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
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
            and interview.answer_mode == "text"
            and current is not None
            and current.status == "asked"
            and current.answer_text is None
            and pending is None
        ):
            question = {
                "type": "question",
                "persona": current.persona,
                "text": current.question_text,
                "turn": current.turn_no,
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
        )


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

    async def receive(self) -> object:
        receiving = asyncio.create_task(self.socket.receive_json())
        closing = asyncio.create_task(self.closed.wait())
        try:
            await asyncio.wait((receiving, closing), return_when=asyncio.FIRST_COMPLETED)
            if closing.done():
                raise WebSocketDisconnect()
            return receiving.result()
        finally:
            for task in (receiving, closing):
                task.cancel()
            with CancelScope(shield=True):
                await asyncio.gather(receiving, closing, return_exceptions=True)

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
        event = _error("question_failed")
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


async def _execute(connection: _Connection, user_id: UUID, turn: int, text: str) -> AnswerExecution:
    state = connection.socket.app.state
    config = state.settings
    current = await _read_state(connection.socket, user_id, connection.interview_id)
    if current.question is None or current.question["turn"] != turn:
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
    with CancelScope(shield=True):
        # 연결 인계용 유한 표식이다. 호출·재시도 대기·근거 조회 예산과 정리 여유를 포함한다.
        lifetime = ceil(
            6 * llm.llm_timeout_seconds + config.director_evidence_timeout_seconds + 120
        )
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
            lifetime,
        )
        if not claimed:
            raise AgentStateError("connection_replaced_or_busy")
        try:
            result = await process_answer(
                state.session_factory,
                user_id=user_id,
                interview_id=connection.interview_id,
                turn_no=turn,
                text=text,
                call_id=uuid4(),
                settings=llm,
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
        finally:
            with suppress(RedisError):
                await _script(connection.redis, _RELEASE, 1, connection.work, connection.nonce)
    return result


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
    initial = await _read_state(socket, user_id, interview_id)
    if initial.status in {"completed", "abandoned"}:
        await _deny(socket, "session_expired")
        return
    nonce = secrets.token_urlsafe(32)
    assert raw is not None
    connection = _Connection(socket, redis, session_id, interview_id, raw, nonce)
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
                raw_answer = await connection.receive()
            except (ValueError, KeyError):
                await connection.send(_error("answer_rejected"))
                continue
            # 로그인 인증은 handshake에서 확정한다. 답변에서는 면접 연결 소유권만 확인한다.
            if not await connection.refresh():
                await connection.close(1008)
                return
            parsed = _answer(raw_answer)
            if isinstance(parsed, str):
                await connection.send(_error(parsed))
                continue
            turn, text = parsed
            try:
                result = await _execute(connection, user_id, turn, text)
            except AgentStateError as exc:
                if exc.reason == "answer_turn_invalid":
                    await connection.send(_error("answer_stale_turn"))
                    continue
                await connection.send(_error("question_failed"))
                await connection.close()
                return
            if result.failure is not None or result.discard_reason is not None:
                await connection.send(_error("question_failed"))
                await connection.close()
                return
            if not await connection.restore(user_id):
                return
    except WebSocketDisconnect:
        connection.connected = False
    except Exception as exc:
        logger.error("interview_ws_failed", exception_type=type(exc).__name__)
        await connection.send(_error("question_failed"))
        await connection.close(1011)
    finally:
        for task in (heartbeat, watcher):
            if task is not None:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
        with CancelScope(shield=True), suppress(RedisError):
            await _script(redis, _RELEASE, 1, connection.lock, nonce)
        with CancelScope(shield=True), suppress(RedisError):
            await cast(Callable[[], Awaitable[None]], control.aclose)()
