"""무료 문자 예산의 명시적 초기화·원자 예약.

Redis가 비었거나 재시작되면 자동으로 새 무료 한도를 만들지 않는다. 운영자가
Cloud의 실제 남은 허용량과 진행 중 호출 부재를 확인한 뒤 초기화해야 한다.
다른 앱의 Cloud 사용량은 이 카운터가 관측하거나 제어하지 못한다.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, cast

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.integrations.tts.google import CharacterReservation, TtsError

_INITIALIZE = """
local used = tonumber(redis.call('HGET', KEYS[1], 'used') or '0')
local pending = tonumber(redis.call('HGET', KEYS[1], 'pending') or '0')
local uncertain = tonumber(redis.call('HGET', KEYS[1], 'uncertain') or '0')
local prior = tonumber(redis.call('HGET', KEYS[1], 'limit') or ARGV[2])
local available = math.max(0, tonumber(ARGV[3]) - pending - uncertain)
local limit = math.min(tonumber(ARGV[2]), prior, used + available)
redis.call('HSET', KEYS[1], 'run_id', ARGV[1], 'limit', limit,
  'used', used, 'pending', pending, 'uncertain', uncertain, 'initialization_metadata', ARGV[4])
return {limit, used}
"""
_RESERVE = """
local epoch = redis.call('HGET', KEYS[1], 'run_id')
if not epoch then return -1 end
if epoch ~= ARGV[1] then return -2 end
local used = tonumber(redis.call('HGET', KEYS[1], 'used'))
local limit = tonumber(redis.call('HGET', KEYS[1], 'limit'))
if not used or not limit then return -3 end
local amount = tonumber(ARGV[2])
if used + amount > math.min(limit, tonumber(ARGV[3])) then return -4 end
redis.call('HINCRBY', KEYS[1], 'used', amount)
redis.call('HINCRBY', KEYS[1], 'pending', amount)
redis.call('HSET', KEYS[1], 'request:' .. ARGV[4], ARGV[2] .. ':reserved')
return used + amount
"""
_SETTLE = """
local epoch = redis.call('HGET', KEYS[1], 'run_id')
if not epoch or epoch ~= ARGV[1] then return 0 end
local field = 'request:' .. ARGV[2]
local expected = ARGV[3] .. ':reserved'
local final = ARGV[3] .. ':' .. ARGV[4]
local current = redis.call('HGET', KEYS[1], field)
if current == final then return 1 end
if current ~= expected then return 0 end
redis.call('HSET', KEYS[1], field, final)
redis.call('HINCRBY', KEYS[1], 'pending', -tonumber(ARGV[3]))
if ARGV[4] == 'rejected' then
  redis.call('HINCRBY', KEYS[1], 'used', -tonumber(ARGV[3]))
  redis.call('HINCRBY', KEYS[1], 'rejected', tonumber(ARGV[3]))
elseif ARGV[4] == 'uncertain' then
  redis.call('HINCRBY', KEYS[1], 'uncertain', tonumber(ARGV[3]))
end
return 1
"""


@dataclass(frozen=True)
class BudgetSnapshot:
    period: str
    limit: int
    used: int
    remaining: int


def _identity(project: str, monthly_limit: int, period: str | None) -> tuple[str, str]:
    if not isinstance(project, str) or not project.strip() or len(project) > 256:
        raise TtsError("budget_unconfigured")
    if type(monthly_limit) is not int or not 0 < monthly_limit <= 1000000:
        raise TtsError("budget_unconfigured")
    value = period or datetime.now(UTC).strftime("%Y-%m")
    if not re.fullmatch(r"[0-9]{4}-(?:0[1-9]|1[0-2])", value):
        raise TtsError("invalid_budget_period")
    digest = hashlib.sha256(project.encode()).hexdigest()
    return value, f"tts:character-budget:{digest}:{value}"


async def _run_id(redis: Redis) -> str:
    try:
        info = cast(Callable[..., Awaitable[dict[str, object]]], redis.info)
        raw = (await info("server")).get("run_id")
    except RedisError:
        raise TtsError("budget_unavailable") from None
    if not isinstance(raw, str) or not raw:
        raise TtsError("budget_unavailable")
    return raw


async def _eval(redis: Redis, script: str, key: str, *args: object) -> object:
    try:
        execute = cast(Callable[..., Awaitable[object]], redis.execute_command)
        return await execute("EVAL", script, 1, key, *args)
    except RedisError:
        raise TtsError("budget_unavailable") from None


async def initialize_budget(
    redis: Redis,
    *,
    project: str,
    remaining_characters: int,
    monthly_limit: int,
    period: str | None = None,
    basis: str = "operator_confirmed_remaining",
) -> BudgetSnapshot:
    """운영자가 확인한 잔여량으로 초기화한다. 호출·월 전환 경로에서 자동 호출하지 않는다.

    재조정은 알려진 소비를 보존하고 기존 상한을 올리지 않는다. 과금 여부가 불명확한
    호출과 진행 중 예약도 잔여량에서 보수적으로 빼므로 실제 Cloud 무료량보다 적게 쓸 수 있다.
    """
    selected, key = _identity(project, monthly_limit, period)
    if type(remaining_characters) is not int or remaining_characters < 0:
        raise TtsError("invalid_budget_allowance")
    if basis not in {
        "operator_confirmed_remaining",
        "cloud_usage_confirmed",
        "user_confirmed_complete_history",
    }:
        raise TtsError("invalid_budget_basis")
    metadata = json.dumps(
        {
            "basis": basis,
            "initializedAt": datetime.now(UTC).isoformat(),
            "period": selected,
            "monthlyLimit": monthly_limit,
            "confirmedRemaining": remaining_characters,
            "formula": (
                "min(monthlyLimit, priorLimit, used + "
                "max(0, confirmedRemaining - pending - uncertain))"
            ),
        },
        separators=(",", ":"),
    )
    result = await _eval(
        redis, _INITIALIZE, key, await _run_id(redis), monthly_limit, remaining_characters, metadata
    )
    if not isinstance(result, list) or len(result) != 2 or any(type(x) is not int for x in result):
        raise TtsError("budget_unavailable")
    limit, used = result
    return BudgetSnapshot(selected, limit, used, max(0, limit - used))


class RedisCharacterBudget:
    def __init__(
        self, redis: Redis, *, project: str, monthly_limit: int, period: str | None = None
    ) -> None:
        self.period, self.key = _identity(project, monthly_limit, period)
        self.redis, self.monthly_limit = redis, monthly_limit

    async def reserve(self, text: str) -> CharacterReservation:
        characters = len(text)
        if not characters:
            raise TtsError("empty_text")
        token = secrets.token_hex(16)
        result = await _eval(
            self.redis,
            _RESERVE,
            self.key,
            await _run_id(self.redis),
            characters,
            self.monthly_limit,
            token,
        )
        reasons = {
            -1: "budget_uninitialized",
            -2: "budget_epoch_changed",
            -3: "budget_unavailable",
            -4: "budget_exhausted",
        }
        if type(result) is not int:
            raise TtsError("budget_unavailable")
        if result < 0:
            raise TtsError(reasons.get(result, "budget_unavailable"))
        return CharacterReservation(token, characters, self.key)

    async def settle(
        self,
        reservation: CharacterReservation,
        outcome: Literal["success", "uncertain", "rejected"],
    ) -> None:
        if reservation.budget_key != self.key or outcome not in {
            "success",
            "uncertain",
            "rejected",
        }:
            raise TtsError("invalid_reservation")
        result = await _eval(
            self.redis,
            _SETTLE,
            self.key,
            await _run_id(self.redis),
            reservation.token,
            reservation.characters,
            outcome,
        )
        if result != 1:
            raise TtsError("budget_unavailable")
