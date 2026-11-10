"""현재 API 컨테이너에 읽기 전용 TTS 점검을 주입하고 안전한 요약만 출력한다."""

import argparse
import base64
import hashlib
import json
import re
import shlex
from pathlib import Path

from ssm_transport import install_signal_handlers, run

NAMES = frozenset(
    {
        "provider",
        "authentication",
        "voices",
        "budget_configuration",
        "tts",
        "redis",
        "tts_budget",
        "settings",
        "probe",
        "google_voice_catalog",
    }
)
CODES = frozenset(
    {
        "ready",
        "provider_not_configured",
        "unsupported_provider",
        "credentials_missing",
        "api_key_selected",
        "static_access_token_requires_refresh",
        "invalid_voice_mapping",
        "unsupported_free_voice",
        "budget_unconfigured",
        "invalid_configuration",
        "redis_unavailable",
        "budget_uninitialized",
        "budget_epoch_changed",
        "budget_exhausted",
        "budget_unavailable",
        "settings_invalid",
        "probe_unavailable",
        "voice_catalog_available",
        "catalog_access_denied",
        "catalog_unavailable",
        "voice_unavailable",
    }
)
GOOGLE_REASONS = frozenset(
    {
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
)
COUNTS = frozenset(
    {
        "voiceCount",
        "monthlyLimit",
        "budgetLimit",
        "used",
        "pending",
        "uncertain",
        "remaining",
    }
)
REQUIRED = frozenset(
    {
        "provider",
        "authentication",
        "voices",
        "budget_configuration",
        "google_voice_catalog",
        "redis",
        "tts_budget",
    }
)
CONTAINER_CODES = frozenset(
    {
        "ready",
        "tts_not_ready",
        "api_container_unavailable",
        "runtime_changed_during_check",
        "invalid_container_metadata",
    }
)
STAMP = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9:.]{8,24}Z")


def build_command(payload):
    if not isinstance(payload, bytes) or not 0 < len(payload) <= 30000:
        raise ValueError("invalid_probe")
    encoded = base64.b64encode(payload).decode("ascii")
    digest = hashlib.sha256(payload).hexdigest()
    select = (
        "docker ps -q --no-trunc --filter label=com.docker.compose.project=devon-deploy "
        "--filter label=com.docker.compose.service=api"
    )
    inspect = "docker inspect --format '{{.Id}} {{.Image}} {{.State.StartedAt}} {{.State.Status}}'"
    script = (
        "set -Eeuo pipefail; container=''; image=''; started=''; "
        'emit() { printf \'{"schemaVersion":1,"event":"tts_diagnostic",'
        '"status":"%s","code":"%s","containerId":"%s",'
        '"imageId":"%s","startedAt":"%s",'
        f'"probeSha256":"{digest}"}}\\n\' '
        '"$1" "$2" "$container" "$image" "$started"; }; '
        'fail() { emit failed "$1"; exit 1; }; '
        f'container="$({select} 2>/dev/null)" || fail api_container_unavailable; '
        '[[ $container =~ ^[0-9a-f]{64}$ ]] || { container=""; fail api_container_unavailable; }; '
        f'before="$({inspect} "$container" 2>/dev/null)" || fail api_container_unavailable; '
        'read -r before_id image started state <<<"$before"; '
        '[[ $before_id == "$container" && $image =~ ^sha256:[0-9a-f]{64}$ '
        "&& $started =~ ^[0-9TZ:.+-]{20,40}$ && $state == running ]] "
        '|| { image=""; started=""; fail invalid_container_metadata; }; probe_status=0; '
        f"printf '%s' '{encoded}' | base64 -d | "
        'docker exec -i "$container" python -B - 2>/dev/null || probe_status=$?; '
        f'after="$({inspect} "$container" 2>/dev/null)" || fail runtime_changed_during_check; '
        f'current="$({select} 2>/dev/null)" || fail runtime_changed_during_check; '
        '[[ $current == "$container" && $before == "$after" ]] '
        "|| fail runtime_changed_during_check; "
        "[[ $probe_status == 0 ]] || fail tts_not_ready; emit passed ready"
    )
    return (
        "sudo -u ubuntu -H timeout --signal=TERM --kill-after=5s 60s bash -c "
        + shlex.quote(script),
        digest,
    )


def allowed(value, choices):
    return isinstance(value, str) and value in choices


def probe_report(value):
    if (
        value.get("schemaVersion") != 1
        or value.get("phase") != "tts"
        or type(value.get("ok")) is not bool
    ):
        return None
    original = value.get("checks")
    if not isinstance(original, list):
        return None
    checks = []
    for row in original[:30]:
        if not isinstance(row, dict) or not allowed(row.get("name"), NAMES):
            continue
        if not allowed(row.get("status"), {"ready", "warning", "error"}):
            continue
        details = {}
        source = row.get("details", {})
        for key, item in source.items() if isinstance(source, dict) else []:
            if any(
                (
                    key in COUNTS and type(item) is int and 0 <= item <= 10**12,
                    key == "authentication" and allowed(item, {"access_token", "api_key"}),
                    key == "period"
                    and isinstance(item, str)
                    and re.fullmatch(r"[0-9]{4}-(?:0[1-9]|1[0-2])", item),
                    key == "httpStatus" and type(item) is int and 100 <= item <= 599,
                    key == "reason" and allowed(item, GOOGLE_REASONS),
                )
            ):
                details[key] = item
        checks.append(
            {
                "name": row["name"],
                "status": row["status"],
                "code": row["code"] if allowed(row.get("code"), CODES) else "unrecognized_code",
                "details": details,
            }
        )
    external = value.get("externalRead", {})
    catalog = external.get("googleVoiceCatalog") if isinstance(external, dict) else None
    synthesis = external.get("synthesisRequests") if isinstance(external, dict) else None
    return {
        "ok": value["ok"]
        and bool(checks)
        and len(checks) == len(original)
        and all(row["status"] != "error" and row["code"] != "unrecognized_code" for row in checks),
        "checks": checks,
        "externalRead": {
            "googleVoiceCatalog": catalog if type(catalog) is bool else None,
            "synthesisRequests": 0 if type(synthesis) is int and synthesis == 0 else None,
        },
        "notVerified": [
            "google_authentication",
            "google_synthesis",
            "browser_playback",
        ],
    }


def sanitize(stdout, stderr):
    report, completion = None, None
    for line in str(stdout)[:24000].splitlines()[:30]:
        try:
            value = json.loads(line)
        except (ValueError, TypeError):
            continue
        if not isinstance(value, dict):
            continue
        candidate = probe_report(value)
        if candidate is not None:
            report = candidate
        elif value.get("event") == "tts_diagnostic":
            completion = {
                "status": value["status"]
                if allowed(value.get("status"), {"passed", "failed"})
                else "failed",
                "code": value["code"]
                if allowed(value.get("code"), CONTAINER_CODES)
                else "unrecognized_code",
            }
            for field, pattern in (
                ("containerId", r"[0-9a-f]{64}"),
                ("imageId", r"sha256:[0-9a-f]{64}"),
                ("probeSha256", r"[0-9a-f]{64}"),
            ):
                item = value.get(field)
                completion[field] = (
                    item if isinstance(item, str) and re.fullmatch(pattern, item) else None
                )
            started = value.get("startedAt")
            completion["startedAt"] = (
                started if isinstance(started, str) and STAMP.fullmatch(started) else None
            )
    return {"report": report, "completion": completion, "stderrPresent": bool(stderr)}


def verified(value, digest):
    report, completion = value.get("report"), value.get("completion")
    return bool(
        isinstance(report, dict)
        and report["ok"]
        and REQUIRED <= {row["name"] for row in report["checks"]}
        and report["externalRead"]["googleVoiceCatalog"] is True
        and report["externalRead"]["synthesisRequests"] == 0
        and isinstance(completion, dict)
        and completion.get("status") == "passed"
        and completion.get("code") == "ready"
        and completion.get("probeSha256") == digest
        and all(completion.get(field) for field in ("containerId", "imageId", "startedAt"))
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instance-id", required=True)
    parser.add_argument("--revision", required=True)
    args = parser.parse_args()
    install_signal_handlers()
    if not re.fullmatch(r"[0-9a-f]{40}", args.revision):
        result = {"ok": False, "transportCode": "invalid_revision"}
    else:
        try:
            payload = Path(__file__).with_name("tts_probe.py").read_bytes()
            command, digest = build_command(payload)
            result = run(
                args.instance_id,
                command,
                sanitize,
                lambda value: verified(value, digest),
            )
            result["probeRevision"] = args.revision
        except (OSError, ValueError):
            result = {"ok": False, "transportCode": "probe_unavailable"}
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
