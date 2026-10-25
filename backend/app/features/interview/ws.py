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
from redis.asyncio import Redis
from redis.asyncio.client import PubSub
from redis.exceptions import RedisError
from sqlalchemy import select
from starlette.responses import JSONResponse

from app.agents.director.tools import EvidenceLimits
from app.core.deps import current_user
from app.core.errors import AppError
from app.core.logging import get_logger
from app.db.models import InterviewSession, LLMCallRecord, Repository
from app.features.interview.agent_context import AgentStateError
from app.features.interview.director_service import AnswerExecution, process_answer
from app.features.interview.queries import list_turns
from app.features.interview.schemas import InterviewLastError
from app.features.interview.service import REALTIME_SESSION_TTL_SECONDS, _reverse_key, _rt_key
from app.shared.enums import Reason

router = APIRouter(prefix="/ws/interviews", tags=["interview"])
logger = get_logger(__name__)
_SESSION_ID = re.compile(r"[A-Za-z0-9_-]{43}")
_LEASE_SECONDS = 30
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
        turns = await list_turns(db, interview_id=interview_id)
        pending = await db.scalar(
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
        return _State(interview.status, question, snapshot, interview.last_error)
