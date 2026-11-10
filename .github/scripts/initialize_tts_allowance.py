"""사용자가 지정한 문자 허용량을 현재 API의 비어 있는 장부에 한 번 등록한다."""

import argparse
import json
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

from diagnose_tts import build_command
from diagnose_tts import sanitize as container_result
from ssm_transport import install_signal_handlers, run

# 원문 예외·프로젝트·키를 출력하지 않고 결과 코드와 집계만 허용한다.
CODES = frozenset(
    {
        "ready",
        "invalid_request",
        "settings_invalid",
        "configuration_mismatch",
        "budget_already_initialized",
        "ledger_not_empty",
        "runtime_changed",
        "period_changed",
        "redis_unavailable",
        "budget_unavailable",
        "initialization_failed",
        "timeout",
        "timeout_not_supported",
        "watch_conflict",
        "invalid_period",
        "invalid_allowance",
        "invalid_authorization",
        "settings_unavailable",
        "redis_epoch_changed",
        "month_changed",
        "concurrent_change",
        "existing_ledger",
        "operation_failed",
        "invalid_configuration",
        "unsupported_timeout",
        "unsupported_tts_timeout",
        "allowance_exceeds_configuration",
        "ledger_exists",
        "unexpected_initialization_command",
        "invalid_initialization_result",
        "verification_failed",
        "operation_interrupted",
        "unauthorized",
        "rate_limited",
        "provider_error",
        "invalid_response",
        "audio_too_large",
        "invalid_audio",
        "budget_uninitialized",
        "budget_epoch_changed",
        "budget_exhausted",
    }
)


def validate_request(requested, period):
    if type(requested) is not int or not 0 < requested <= 1000000:
        raise ValueError("invalid_allowance")
    if not isinstance(period, str) or not re.fullmatch(r"[0-9]{4}-(?:0[1-9]|1[0-2])", period):
        raise ValueError("invalid_period")
    if period != datetime.now(UTC).strftime("%Y-%m"):
        raise ValueError("invalid_period")


def build_payload(requested, period, operation_id, authorized_at, *, smoke=False):
    validate_request(requested, period)
    if not isinstance(operation_id, str) or not re.fullmatch(r"[0-9a-f]{32}", operation_id):
        raise ValueError("invalid_operation")
    if not isinstance(authorized_at, str) or not re.fullmatch(r"[0-9T:.+Z-]{20,40}", authorized_at):
        raise ValueError("invalid_authorization")
    values = {
        "REQUESTED_CHARACTERS": requested,
        "EXPECTED_PERIOD": period,
        "AUTHORIZED_AT": authorized_at,
        "OPERATION_ID": operation_id,
    }
    prefix = "\n".join(f"{key} = {value!r}" for key, value in values.items()) + "\n"
    source = (
        Path(__file__)
        .with_name("tts_smoke_payload.py" if smoke else "tts_allowance_payload.py")
        .read_text("utf-8")
    )
    return (prefix + source).encode("utf-8")


def sanitize(stdout, stderr):
    result = container_result(stdout, stderr)
    result["report"] = None
    if not isinstance(stdout, str) or len(stdout) > 16000:
        return result
    for line in stdout.splitlines():
        try:
            value = json.loads(line)
        except (ValueError, TypeError):
            continue
        if (
            not isinstance(value, dict)
            or value.get("schemaVersion") != 1
            or value.get("phase") not in ("tts_allowance", "tts_smoke")
        ):
            continue
        if type(value.get("ok")) is not bool:
            continue
        code = value.get("code")
        safe = {
            "ok": value["ok"],
            "phase": value["phase"],
            "code": code if isinstance(code, str) and code in CODES else "invalid_report",
        }
        for field in ("period", "operationId"):
            pattern = r"[0-9]{4}-(?:0[1-9]|1[0-2])" if field == "period" else r"[0-9a-f]{32}"
            item = value.get(field)
            if isinstance(item, str) and re.fullmatch(pattern, item):
                safe[field] = item
        amount = value.get("requestedCharacters")
        if type(amount) is int and 0 < amount <= 1000000:
            safe["requestedCharacters"] = amount
        if value.get("allowanceSource") == "user_requested_amount":
            safe["allowanceSource"] = "user_requested_amount"
        if value.get("cloudUsageVerified") is False:
            safe["cloudUsageVerified"] = False
        snapshot = value.get("snapshot")
        if isinstance(snapshot, dict) and all(
            type(snapshot.get(k)) is int and 0 <= snapshot[k] <= 1000000
            for k in ("limit", "used", "remaining")
        ):
            safe["snapshot"] = {k: snapshot[k] for k in ("limit", "used", "remaining")}
        for field in ("applied", "applicationUncertain"):
            if type(value.get(field)) is bool:
                safe[field] = value[field]
        if "applied" in value and value["applied"] is None:
            safe["applied"] = None
        if value.get("mutationState") in ("not_applied", "applied", "unknown"):
            safe["mutationState"] = value["mutationState"]
        for field in ("audioBytes", "characters", "synthAttempts"):
            item = value.get(field)
            if type(item) is int and 0 <= item <= 2097152:
                safe[field] = item
        audio_hash = value.get("audioSha256")
        if isinstance(audio_hash, str) and re.fullmatch(r"[0-9a-f]{64}", audio_hash):
            safe["audioSha256"] = audio_hash
        if value.get("mp3Header") is True:
            safe["mp3Header"] = True
        result["report"] = safe
    return result


def verified(value, digest, requested, period, operation_id, *, smoke=False):
    report, completion = value.get("report"), value.get("completion")
    if not isinstance(report, dict) or not isinstance(completion, dict):
        return False
    snapshot = report.get("snapshot", {})
    operation_ready = (
        (
            report.get("phase") == "tts_smoke"
            and report.get("synthAttempts") == 1
            and report.get("mp3Header") is True
            and report.get("audioBytes", 0) >= 64
            and bool(report.get("audioSha256"))
            and report.get("characters", 0) > 0
        )
        if smoke
        else (
            report.get("phase") == "tts_allowance"
            and report.get("applied") is True
            and report.get("mutationState") == "applied"
        )
    )
    return bool(
        operation_ready
        and report.get("ok") is True
        and report.get("code") == "ready"
        and report.get("requestedCharacters") == requested
        and report.get("period") == period
        and report.get("operationId") == operation_id
        and report.get("allowanceSource") == "user_requested_amount"
        and report.get("cloudUsageVerified") is False
        and snapshot.get("limit") == requested
        and 0 <= snapshot.get("used", -1) <= requested
        and snapshot.get("remaining") == requested - snapshot.get("used", -1)
        and completion.get("status") == "passed"
        and completion.get("code") == "ready"
        and completion.get("probeSha256") == digest
        and all(completion.get(k) for k in ("containerId", "imageId", "startedAt"))
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instance-id", required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--characters", type=int, required=True)
    parser.add_argument("--period", required=True)
    parser.add_argument("--authorization", required=True)
    parser.add_argument(
        "--smoke", action="store_true", help="같은 예산을 사용해 짧은 실제 합성을 한 번 확인"
    )
    args = parser.parse_args()
    install_signal_handlers()
    result = {"ok": False, "transportCode": "invalid_request"}
    if (
        re.fullmatch(r"[0-9a-f]{40}", args.revision)
        and args.authorization == "APPLY_OPERATOR_ALLOWANCE"
    ):
        try:
            operation_id = uuid.uuid4().hex
            payload = build_payload(
                args.characters,
                args.period,
                operation_id,
                datetime.now(UTC).isoformat(),
                smoke=args.smoke,
            )
            command, digest = build_command(payload, timeout_seconds=120)
            result = run(
                args.instance_id,
                command,
                sanitize,
                lambda value: verified(
                    value, digest, args.characters, args.period, operation_id, smoke=args.smoke
                ),
                execution_seconds=150,
            )
            result.update(probeRevision=args.revision, operationId=operation_id)
        except (OSError, ValueError):
            result = {"ok": False, "transportCode": "invalid_request"}
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
