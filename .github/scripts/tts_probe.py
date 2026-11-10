"""현재 API 이미지의 TTS 준비와 Google 음성 목록을 읽는다. 합성·예산 변경은 하지 않는다."""

import asyncio
import json
import sys
from collections.abc import Mapping

import httpx
from redis.asyncio import Redis

from app.core.config import get_settings
from app.features.interview.tts_budget import RedisCharacterBudget

GOOGLE_REASONS = {
    "SERVICE_DISABLED",
    "API_KEY_INVALID",
    "PERMISSION_DENIED",
    "UNAUTHENTICATED",
    "USER_PROJECT_DENIED",
    "BILLING_DISABLED",
    "ACCESS_TOKEN_EXPIRED",
    "ACCESS_TOKEN_SCOPE_INSUFFICIENT",
    "RATE_LIMIT_EXCEEDED",
    "RESOURCE_EXHAUSTED",
    "UNAVAILABLE",
    "UNKNOWN",
}
_catalog_attempted = False


async def catalog_check(settings):
    global _catalog_attempted
    _catalog_attempted = True
    details = {}
    code = "catalog_unavailable"
    try:
        token = settings.tts_access_token
        if token is not None and token.get_secret_value().strip():
            headers = {"Authorization": "Bearer " + token.get_secret_value()}
            if settings.tts_budget_project:
                headers["X-Goog-User-Project"] = settings.tts_budget_project
        else:
            headers = {"X-Goog-Api-Key": settings.tts_api_key.get_secret_value()}
        async with httpx.AsyncClient(timeout=8, trust_env=False, follow_redirects=False) as client:
            async with client.stream(
                "GET",
                "https://texttospeech.googleapis.com/v1/voices?languageCode=ko-KR",
                headers=headers,
            ) as response:
                details["httpStatus"] = response.status_code
                body = bytearray()
                async for chunk in response.aiter_bytes(chunk_size=16384):
                    body.extend(chunk)
                    if len(body) > 262144:
                        raise ValueError("response_too_large")
                payload = json.loads(body)
        if response.status_code == 200:
            voices = payload.get("voices")
            if not isinstance(voices, list):
                raise ValueError("invalid_response")
            available = {
                item.get("name")
                for item in voices
                if isinstance(item, dict) and isinstance(item.get("name"), str)
            }
            configured = list(settings.tts_voice_map.values())
            details["voiceCount"] = sum(voice in available for voice in configured)
            code = (
                "voice_catalog_available"
                if all(voice in available for voice in configured)
                else "voice_unavailable"
            )
        else:
            error = payload.get("error", {}) if isinstance(payload, dict) else {}
            error = error if isinstance(error, dict) else {}
            reason = error.get("status")
            for item in error.get("details", []) if isinstance(error.get("details"), list) else []:
                if isinstance(item, dict) and item.get("reason") in GOOGLE_REASONS:
                    reason = item["reason"]
                    break
            details["reason"] = (
                reason if isinstance(reason, str) and reason in GOOGLE_REASONS else "UNKNOWN"
            )
            code = (
                "catalog_access_denied"
                if response.status_code in (401, 403)
                else "catalog_unavailable"
            )
    except Exception:
        pass
    return {
        "name": "google_voice_catalog",
        "status": "ready" if code == "voice_catalog_available" else "error",
        "code": code,
        "details": details,
    }


def result(checks):
    return {
        "schemaVersion": 1,
        "phase": "tts",
        "ok": all(item["status"] != "error" for item in checks),
        "checks": checks,
        "notVerified": [
            "google_authentication",
            "google_synthesis",
            "browser_playback",
        ],
        "externalRead": {
            "googleVoiceCatalog": _catalog_attempted,
            "synthesisRequests": 0,
        },
    }


async def inspect_tts():
    global _catalog_attempted
    _catalog_attempted = False
    checks = []

    def add(name, status, code, **details):
        checks.append({"name": name, "status": status, "code": code, "details": details})

    try:
        settings = get_settings()
    except Exception:
        add("settings", "error", "settings_invalid")
        return result(checks)

    provider = settings.tts_provider
    provider_code = "provider_not_configured" if not provider else "unsupported_provider"
    add(
        "provider",
        "ready" if provider == "google_cloud" else "error",
        "ready" if provider == "google_cloud" else provider_code,
    )
    token = settings.tts_access_token
    key = settings.tts_api_key
    if token is not None and token.get_secret_value().strip():
        add(
            "authentication",
            "warning",
            "static_access_token_requires_refresh",
            authentication="access_token",
        )
    elif key is not None and key.get_secret_value().strip():
        add("authentication", "ready", "api_key_selected", authentication="api_key")
    else:
        add("authentication", "error", "credentials_missing")

    voices = settings.tts_voice_map
    roles = {"tech_lead", "domain_lead", "hr_manager"}
    valid_mapping = (
        isinstance(voices, Mapping)
        and set(voices) == roles
        and all(isinstance(voice, str) and voice.strip() for voice in voices.values())
    )
    if not valid_mapping:
        add("voices", "error", "invalid_voice_mapping")
    elif settings.tts_language_code != "ko-KR" or any(
        not voice.startswith("ko-KR-Chirp3-HD-") for voice in voices.values()
    ):
        add("voices", "error", "unsupported_free_voice")
    else:
        add("voices", "ready", "ready", voiceCount=3)

    limit = settings.tts_monthly_character_limit
    project = settings.tts_budget_project
    budget_configured = (
        type(limit) is int
        and 0 < limit <= 1000000
        and isinstance(project, str)
        and bool(project.strip())
        and len(project) <= 256
    )
    add(
        "budget_configuration",
        "ready" if budget_configured else "error",
        "ready" if budget_configured else "budget_unconfigured",
    )
    try:
        # 실제 공급자와 같은 설정 검증을 수행하되 합성 함수는 만들거나 호출하지 않는다.
        settings.require_tts()
    except Exception:
        if not any(item["status"] == "error" for item in checks):
            add("tts", "error", "invalid_configuration")
    if provider == "google_cloud" and any(
        item["name"] == "authentication" and item["status"] != "error" for item in checks
    ):
        try:
            checks.append(await asyncio.wait_for(catalog_check(settings), timeout=10))
        except Exception:
            add("google_voice_catalog", "error", "catalog_unavailable")

    client = None
    try:
        client = Redis.from_url(settings.redis_url, socket_timeout=3, socket_connect_timeout=3)
        if not await asyncio.wait_for(client.ping(), timeout=3):
            raise ValueError("unavailable")
        add("redis", "ready", "ready")
        if not budget_configured:
            return result(checks)
        budget = RedisCharacterBudget(client, project=project, monthly_limit=limit)
        info = await asyncio.wait_for(client.info("server"), timeout=3)
        ledger = await asyncio.wait_for(
            client.hmget(budget.key, ["run_id", "limit", "used", "pending", "uncertain"]),
            timeout=3,
        )
        latest = await asyncio.wait_for(client.info("server"), timeout=3)
        same_period = (
            RedisCharacterBudget(client, project=project, monthly_limit=limit).period
            == budget.period
        )
        if latest.get("run_id") != info.get("run_id") or not same_period:
            add("tts_budget", "error", "budget_unavailable")
        elif not ledger or ledger[0] is None:
            add("tts_budget", "error", "budget_uninitialized", period=budget.period)
        else:
            epoch = ledger[0].decode() if isinstance(ledger[0], bytes) else ledger[0]
            if not isinstance(info.get("run_id"), str) or epoch != info["run_id"]:
                add("tts_budget", "error", "budget_epoch_changed", period=budget.period)
            elif len(ledger) != 5 or any(value is None for value in ledger[1:]):
                add("tts_budget", "error", "budget_unavailable")
            else:
                cap, used, pending, uncertain = (int(value) for value in ledger[1:])
                if min(cap, used, pending, uncertain) < 0 or pending + uncertain > used:
                    add("tts_budget", "error", "budget_unavailable")
                else:
                    remaining = max(0, min(cap, limit) - used)
                    add(
                        "tts_budget",
                        "ready" if remaining else "error",
                        "ready" if remaining else "budget_exhausted",
                        period=budget.period,
                        monthlyLimit=limit,
                        budgetLimit=cap,
                        used=used,
                        pending=pending,
                        uncertain=uncertain,
                        remaining=remaining,
                    )
    except Exception:
        name = "tts_budget" if any(item["name"] == "redis" for item in checks) else "redis"
        add(
            name,
            "error",
            "budget_unavailable" if name == "tts_budget" else "redis_unavailable",
        )
    finally:
        if client is not None:
            try:
                await asyncio.wait_for(client.aclose(), timeout=3)
            except Exception:
                pass
    return result(checks)


def main():
    try:

        async def bounded():
            return await asyncio.wait_for(inspect_tts(), timeout=30)

        report = asyncio.run(bounded())
    except Exception:
        report = result(
            [
                {
                    "name": "probe",
                    "status": "error",
                    "code": "probe_unavailable",
                    "details": {},
                }
            ]
        )
    sys.stdout.write(json.dumps(report, separators=(",", ":")) + "\n")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
