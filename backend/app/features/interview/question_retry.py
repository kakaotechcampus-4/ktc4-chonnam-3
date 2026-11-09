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
