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
from app.features.interview.schemas import QuestionRetryResponse
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
  redis.call('DEL', 'rt:' .. old)
end
redis.call('SET', 'rt:' .. ARGV[1], ARGV[2], 'EX', ARGV[3])
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
    if failed is None:
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
    binding = {
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
    return _Scope(target, previous.id, failed, digest, checked)


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
