"""고정 원격 명령의 전송·유한 대기·취소만 담당하는 공통 SSM 계층."""

import json
import re
import signal
import subprocess
import time

TERMINAL = frozenset(
    {
        "Success",
        "Failed",
        "Cancelled",
        "TimedOut",
        "DeliveryTimedOut",
        "ExecutionTimedOut",
        "Undeliverable",
        "Terminated",
        "InvalidPlatform",
        "AccessDenied",
        "Incomplete",
        "RateExceeded",
    }
)
UUID = re.compile(r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}")


class InvocationPending(Exception):
    """등록 직후 아직 SSM 조회 결과에 명령이 나타나지 않은 상태."""


def aws_cli(arguments):
    response = subprocess.run(
        ["aws", "ssm", *arguments, "--output", "json", "--no-cli-pager"],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    if response.returncode:
        if "InvocationDoesNotExist" in response.stderr:
            raise InvocationPending
        raise RuntimeError("ssm_request_failed")
    value = json.loads(response.stdout)
    if not isinstance(value, dict):
        raise TypeError("invalid_ssm_response")
    return value


def _cancel(aws, command_id, instance_id, sleep):
    try:
        aws(
            [
                "cancel-command",
                "--command-id",
                command_id,
                "--instance-ids",
                instance_id,
            ]
        )
        for _ in range(2):
            value = aws(
                [
                    "get-command-invocation",
                    "--command-id",
                    command_id,
                    "--instance-id",
                    instance_id,
                ]
            )
            if value.get("Status") in TERMINAL:
                return True
            sleep(1)
    except (
        OSError,
        RuntimeError,
        ValueError,
        TypeError,
        KeyError,
        subprocess.SubprocessError,
        InvocationPending,
    ):
        return False
    return False


def run(
    instance_id,
    command,
    sanitize,
    verify,
    *,
    aws=aws_cli,
    sleep=time.sleep,
    now=time.monotonic,
    execution_seconds=75,
):
    """호출자가 만든 고정 명령만 보내고 원문 출력은 sanitizer 밖으로 전달하지 않는다."""
    result = {"ok": False, "transportCode": "ssm_request_failed"}
    command_id = None
    terminal = False
    try:
        if not re.fullmatch(r"i-(?:[0-9a-f]{8}|[0-9a-f]{17})", instance_id):
            raise ValueError("invalid_instance")
        if not isinstance(command, str) or not 0 < len(command.encode()) <= 60000:
            raise ValueError("invalid_command")
        if type(execution_seconds) is not int or not 1 <= execution_seconds <= 1200:
            raise ValueError("invalid_timeout")
        sent = aws(
            [
                "send-command",
                "--instance-ids",
                instance_id,
                "--document-name",
                "AWS-RunShellScript",
                "--timeout-seconds",
                "30",
                "--parameters",
                json.dumps(
                    {
                        "commands": [command],
                        "executionTimeout": [str(execution_seconds)],
                    }
                ),
            ]
        )
        command_id = sent["Command"]["CommandId"]
        if not isinstance(command_id, str) or not UUID.fullmatch(command_id):
            command_id = None
            raise ValueError("invalid_command_id")
        result["commandId"] = command_id
        deadline = now() + execution_seconds + 30
        for _ in range(execution_seconds // 2 + 20):
            if now() >= deadline:
                result["transportCode"] = "remote_timeout"
                break
            try:
                response = aws(
                    [
                        "get-command-invocation",
                        "--command-id",
                        command_id,
                        "--instance-id",
                        instance_id,
                    ]
                )
            except InvocationPending:
                sleep(2)
                continue
            status = response.get("Status")
            if status in TERMINAL or status == "Cancelling":
                terminal = status in TERMINAL
                safe = sanitize(
                    response.get("StandardOutputContent", ""),
                    response.get("StandardErrorContent", ""),
                )
                code = response.get("ResponseCode")
                passed = status == "Success" and type(code) is int and code == 0 and verify(safe)
                result.update(
                    ok=passed,
                    transportCode="ready" if passed else "remote_failed",
                    diagnostic=safe,
                )
                break
            sleep(2)
        else:
            result["transportCode"] = "remote_timeout"
    except (
        OSError,
        RuntimeError,
        ValueError,
        TypeError,
        KeyError,
        subprocess.SubprocessError,
        KeyboardInterrupt,
    ):
        result["transportCode"] = "ssm_request_failed"
    finally:
        if command_id and not terminal:
            result["cancellationConfirmed"] = _cancel(aws, command_id, instance_id, sleep)
    return result


def install_signal_handlers():
    def interrupted(_signum, _frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, interrupted)
