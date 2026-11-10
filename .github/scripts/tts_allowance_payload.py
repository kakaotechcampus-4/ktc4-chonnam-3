"""사용자가 지정한 허용량으로 비어 있는 현재 월 TTS 장부만 최초 등록한다."""

import asyncio
import json
import math
import re
from datetime import UTC, datetime

from redis.asyncio import Redis
from redis.exceptions import ResponseError, WatchError

from app.core.config import get_settings
from app.features.interview.tts_budget import RedisCharacterBudget, initialize_budget


class Refused(Exception):
    """원문 예외 대신 공개 가능한 고정 거절 코드만 전달한다."""


def current_period():
    return datetime.now(UTC).strftime("%Y-%m")


def period_bounds(period):
    year, month = (int(value) for value in period.split("-"))
    start = datetime(year, month, 1, tzinfo=UTC)
    end = datetime(year + (month == 12), month % 12 + 1, 1, tzinfo=UTC)
    return int(start.timestamp()), int(end.timestamp())


class FirstInitialization:
    """기존 초기화 계산과 승인 기록을 WATCH로 보호한 단일 EVAL에 묶는다."""

    def __init__(self, redis, pipeline, key, epoch, period, authorization):
        self.redis, self.pipeline, self.key = redis, pipeline, key
        self.epoch, self.period, self.authorization = epoch, period, authorization
        self.mutation_state = "not_applied"

    async def info(self, section):
        return await self.redis.info(section)

    async def execute_command(self, *arguments):
        if (
            len(arguments) != 8
            or arguments[0] != "EVAL"
            or arguments[2:5] != (1, self.key, self.epoch)
        ):
            raise Refused("unexpected_initialization_command")
        if current_period() != self.period:
            raise Refused("period_changed")
        if (await self.redis.info("server")).get("run_id") != self.epoch:
            raise Refused("redis_epoch_changed")
        start, end = period_bounds(self.period)
        # EXEC 직전 월 전환도 Redis 시계로 차단한다. 예산 계산은 기존 Lua를 그대로 사용한다.
        script = (
            "local now = tonumber(redis.call('TIME')[1]); "
            f"if now < {start} or now >= {end} then "
            "return redis.error_reply('TTS_PERIOD_CHANGED') end; "
            "if redis.call('EXISTS', KEYS[1]) ~= 0 then "
            "return redis.error_reply('TTS_LEDGER_EXISTS') end; "
            "local function initialize_existing()\n"
            + arguments[1]
            + "\nend\nlocal result = initialize_existing(); "
            "redis.call('HSET', KEYS[1], 'operator_allowance_authorization', ARGV[5]); "
            "return result"
        )
        self.pipeline.multi()
        self.pipeline.execute_command("EVAL", script, *arguments[2:], self.authorization)
        self.mutation_state = "unknown"
        try:
            responses = await self.pipeline.execute(raise_on_error=False)
        except WatchError:
            self.mutation_state = "not_applied"
            raise Refused("concurrent_change") from None
        if (
            isinstance(responses, list)
            and len(responses) == 1
            and isinstance(responses[0], ResponseError)
        ):
            error = responses[0]
            if str(error) in {"TTS_PERIOD_CHANGED", "TTS_LEDGER_EXISTS"}:
                self.mutation_state = "not_applied"
                raise Refused(
                    "period_changed" if str(error) == "TTS_PERIOD_CHANGED" else "ledger_exists"
                ) from None
            raise error
        if (
            not isinstance(responses, list)
            or len(responses) != 1
            or not isinstance(responses[0], list)
            or len(responses[0]) != 2
            or any(type(value) is not int for value in responses[0])
        ):
            raise Refused("invalid_initialization_result")
        self.mutation_state = "applied"
        return responses[0]


async def initialize_allowance(requested, period, authorized_at, operation_id, expected_epoch=None):
    result = {
        "schemaVersion": 1,
        "phase": "tts_allowance",
        "ok": False,
        "code": "initialization_failed",
        "period": period
        if isinstance(period, str) and re.fullmatch(r"\d{4}-\d{2}", period)
        else None,
        "requestedCharacters": requested if type(requested) is int else None,
        "operationId": operation_id
        if isinstance(operation_id, str) and re.fullmatch(r"[0-9a-f]{32}", operation_id)
        else None,
        "allowanceSource": "user_requested_amount",
        "cloudUsageVerified": False,
        "applied": False,
        "mutationState": "not_applied",
    }
    client = adapter = None
    try:
        async with asyncio.timeout(65):
            if type(requested) is not int or not 0 < requested <= 1000000:
                raise Refused("invalid_allowance")
            if not isinstance(period, str) or not re.fullmatch(r"\d{4}-(?:0[1-9]|1[0-2])", period):
                raise Refused("invalid_period")
            if current_period() != period:
                raise Refused("period_changed")
            if not isinstance(operation_id, str) or not re.fullmatch(r"[0-9a-f]{32}", operation_id):
                raise Refused("invalid_authorization")
            stamp = datetime.fromisoformat(authorized_at.replace("Z", "+00:00"))
            if stamp.utcoffset() is None or stamp.strftime("%Y-%m") != period:
                raise Refused("invalid_authorization")
            settings = get_settings()
            tts = settings.require_tts()
            timeout = tts.timeout_seconds
            if not math.isfinite(timeout) or not 0 < timeout <= 25:
                raise Refused("unsupported_tts_timeout")
            if requested > tts.monthly_character_limit:
                raise Refused("allowance_exceeds_configuration")
            client = Redis.from_url(settings.redis_url, socket_timeout=3, socket_connect_timeout=3)
            budget = RedisCharacterBudget(
                client,
                project=tts.budget_project,
                monthly_limit=tts.monthly_character_limit,
                period=period,
            )
            epoch = (await client.info("server")).get("run_id")
            if (
                not isinstance(epoch, str)
                or not epoch
                or (expected_epoch and epoch != expected_epoch)
            ):
                raise Refused("redis_epoch_changed")
            async with client.pipeline(transaction=True) as pipeline:
                await pipeline.watch(budget.key)
                if await pipeline.exists(budget.key):
                    raise Refused("ledger_exists")
                # 빈 장부에서는 신규 합성이 예약되지 않는다. 이전의 유한 합성이 끝날 시간을 둔다.
                await asyncio.sleep(timeout + 5)
                if current_period() != period:
                    raise Refused("period_changed")
                if (await client.info("server")).get("run_id") != epoch:
                    raise Refused("redis_epoch_changed")
                if await pipeline.exists(budget.key):
                    raise Refused("ledger_exists")
                authorization = json.dumps(
                    {
                        "allowanceSource": "user_requested_amount",
                        "cloudUsageVerified": False,
                        "requestedCharacters": requested,
                        "authorizedAt": authorized_at,
                        "operationId": operation_id,
                        "period": period,
                    },
                    separators=(",", ":"),
                )
                adapter = FirstInitialization(
                    client, pipeline, budget.key, epoch, period, authorization
                )
                snapshot = await initialize_budget(
                    adapter,
                    project=tts.budget_project,
                    remaining_characters=requested,
                    monthly_limit=tts.monthly_character_limit,
                    period=period,
                    basis="operator_confirmed_remaining",
                )
            if current_period() != period or (await client.info("server")).get("run_id") != epoch:
                raise Refused("verification_failed")
            ledger = await client.hmget(
                budget.key,
                [
                    "run_id",
                    "limit",
                    "used",
                    "pending",
                    "uncertain",
                    "operator_allowance_authorization",
                ],
            )
            if (
                len(ledger) != 6
                or ledger[0] not in (epoch, epoch.encode())
                or int(ledger[1]) != snapshot.limit
                or any(value is None or int(value) < 0 for value in ledger[2:5])
                or int(ledger[3]) + int(ledger[4]) > int(ledger[2])
                or ledger[5] not in (authorization, authorization.encode())
            ):
                raise Refused("verification_failed")
            # 초기화 직후 실제 요청이 소비했을 수 있으므로 최신 사용량을 읽어 보고한다.
            used = int(ledger[2])
            result.update(
                ok=True,
                code="ready",
                snapshot={
                    "limit": snapshot.limit,
                    "used": used,
                    "remaining": max(0, snapshot.limit - used),
                },
            )
    except Refused as error:
        result["code"] = str(error)
    except asyncio.CancelledError:
        result["code"] = "operation_interrupted"
    except Exception:
        # 설정·연결·공급자 예외 원문에는 비밀값이 섞일 수 있다.
        pass
    finally:
        if adapter is not None:
            result["mutationState"] = adapter.mutation_state
            result["applied"] = {"not_applied": False, "applied": True, "unknown": None}[
                adapter.mutation_state
            ]
        if client is not None:
            try:
                await asyncio.wait_for(client.aclose(), timeout=3)
            except Exception:
                pass
    return result


def main():
    report = asyncio.run(
        initialize_allowance(
            globals().get("REQUESTED_CHARACTERS"),
            globals().get("EXPECTED_PERIOD"),
            globals().get("AUTHORIZED_AT"),
            globals().get("OPERATION_ID"),
            globals().get("EXPECTED_REDIS_EPOCH"),
        )
    )
    print(json.dumps(report, ensure_ascii=False, separators=(",", ":")))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
