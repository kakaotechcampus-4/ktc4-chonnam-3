"""실제 API와 같은 예산을 통과해 짧은 한국어 MP3 합성을 한 번 검증한다."""

import asyncio
import hashlib
import json
from datetime import UTC, datetime

from redis.asyncio import Redis

from app.core.config import get_settings
from app.features.interview.tts_budget import RedisCharacterBudget
from app.integrations.tts.google import GoogleTTSClient, TtsError

TEXT = "음성 확인입니다."


async def smoke(requested, period, operation_id):
    report = {
        "schemaVersion": 1,
        "phase": "tts_smoke",
        "ok": False,
        "code": "verification_failed",
        "period": period,
        "requestedCharacters": requested,
        "operationId": operation_id,
        "allowanceSource": "user_requested_amount",
        "cloudUsageVerified": False,
        "synthAttempts": 0,
        "characters": len(TEXT),
    }
    redis = None
    try:
        if datetime.now(UTC).strftime("%Y-%m") != period:
            report["code"] = "period_changed"
            return report
        settings = get_settings()
        tts = settings.require_tts()
        if tts.timeout_seconds > 25:
            report["code"] = "unsupported_tts_timeout"
            return report
        redis = Redis.from_url(settings.redis_url, socket_timeout=3, socket_connect_timeout=3)
        budget = RedisCharacterBudget(
            redis, project=tts.budget_project, monthly_limit=tts.monthly_character_limit
        )
        if budget.period != period:
            report["code"] = "period_changed"
            return report
        # 예약·정산을 우회하지 않으며 실패나 불명확 응답을 자동 재시도하지 않는다.
        report["synthAttempts"] = 1
        audio = await GoogleTTSClient(tts, budget=budget).synthesize(TEXT, "tech_lead")
        data = audio.data
        mp3 = data.startswith(b"ID3") or (
            len(data) >= 2 and data[0] == 0xFF and data[1] & 0xE0 == 0xE0
        )
        if audio.mime_type != "audio/mpeg" or len(data) < 64 or not mp3:
            report["code"] = "invalid_audio"
            return report
        raw = await redis.hmget(budget.key, ["limit", "used", "pending", "uncertain", "run_id"])
        epoch = (await redis.info("server")).get("run_id")
        saved_epoch = raw[4].decode() if isinstance(raw[4], bytes) else raw[4]
        cap, used, pending, uncertain = map(int, raw[:4])
        if saved_epoch != epoch or budget.period != datetime.now(UTC).strftime("%Y-%m"):
            report["code"] = "redis_epoch_changed"
            return report
        if (
            cap != requested
            or not len(TEXT) <= used <= cap
            or min(pending, uncertain) < 0
            or pending + uncertain > used
        ):
            return report
        report.update(
            ok=True,
            code="ready",
            audioBytes=len(data),
            mp3Header=True,
            audioSha256=hashlib.sha256(data).hexdigest(),
            snapshot={"limit": cap, "used": used, "remaining": cap - used},
        )
    except TtsError as error:
        report["code"] = error.reason
    except Exception:
        report["code"] = "verification_failed"
    finally:
        if redis is not None:
            try:
                await redis.aclose()
            except Exception:
                pass
    return report


if __name__ == "__main__":
    try:
        result = asyncio.run(
            asyncio.wait_for(
                smoke(
                    globals().get("REQUESTED_CHARACTERS"),
                    globals().get("EXPECTED_PERIOD"),
                    globals().get("OPERATION_ID"),
                ),
                40,
            )
        )
    except Exception:
        result = {
            "schemaVersion": 1,
            "phase": "tts_smoke",
            "ok": False,
            "code": "operation_interrupted",
        }
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    raise SystemExit(0 if result["ok"] else 1)
