"""허용량 등록의 입력·출력·운영 실행 경계를 검증한다."""

import ast
import importlib
import io
import json
import shlex
import sys
import unittest
from contextlib import redirect_stdout
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".github/scripts"))
PERIOD = datetime.now(UTC).strftime("%Y-%m")
OPERATION = "a" * 32
DIGEST = "b" * 64
CONTAINER = "c" * 64
IMAGE = "sha256:" + "d" * 64
STARTED = "2026-11-10T12:00:00.000000000Z"


def runner():
    return importlib.import_module("initialize_tts_allowance")


def report():
    return {
        "schemaVersion": 1,
        "phase": "tts_allowance",
        "ok": True,
        "code": "ready",
        "period": PERIOD,
        "requestedCharacters": 1000000,
        "operationId": OPERATION,
        "allowanceSource": "user_requested_amount",
        "cloudUsageVerified": False,
        "applied": True,
        "mutationState": "applied",
        "snapshot": {"limit": 1000000, "used": 0, "remaining": 1000000},
    }


def output(value=None, completion=None):
    end = {
        "schemaVersion": 1,
        "event": "tts_diagnostic",
        "status": "passed",
        "code": "ready",
        "containerId": CONTAINER,
        "imageId": IMAGE,
        "startedAt": STARTED,
        "probeSha256": DIGEST,
    }
    end.update(completion or {})
    return "\n".join(json.dumps(v) for v in (report() if value is None else value, end))


class InputTests(unittest.TestCase):
    def test_current_month_integer_allowance_is_required(self):
        for amount in (1, 1000000):
            runner().validate_request(amount, PERIOD)
        for amount in (True, False, 0, -1, 1000001, 1.5, "1000000", None):
            with self.subTest(amount=amount), self.assertRaises(ValueError):
                runner().validate_request(amount, PERIOD)
        for period in ("2000-01", "2026-00", "2026-13", "2026-1", "2026-11\n", True, None):
            with self.subTest(period=period), self.assertRaises(ValueError):
                runner().validate_request(1000000, period)

    def test_payload_contains_only_validated_python_literals(self):
        with patch.object(Path, "read_text", return_value="PAYLOAD_BODY = True\n"):
            payload = runner().build_payload(
                1000000, PERIOD, OPERATION, "2026-11-10T15:50:00+00:00"
            )
        values = {}
        for node in ast.parse(payload).body[:4]:
            self.assertIsInstance(node, ast.Assign)
            values[node.targets[0].id] = ast.literal_eval(node.value)
        self.assertEqual(values["REQUESTED_CHARACTERS"], 1000000)
        self.assertEqual(values["EXPECTED_PERIOD"], PERIOD)
        self.assertEqual(values["OPERATION_ID"], OPERATION)
        self.assertNotIn("cloud_usage_confirmed", payload.decode())
        for field in ("operation", "date", "period"):
            kwargs = dict(
                requested=1000000,
                period=PERIOD,
                operation_id=OPERATION,
                authorized_at="2026-11-10T15:50:00+00:00",
            )
            key = {"operation": "operation_id", "date": "authorized_at", "period": "period"}[field]
            kwargs[key] = "'; __import__('os').system('echo unsafe'); #"
            with self.subTest(field=field), self.assertRaises(ValueError):
                runner().build_payload(**kwargs)

    def test_remote_deadline_is_bounded_and_default_is_preserved(self):
        default, _ = runner().build_command(b"print('safe')")
        extended, _ = runner().build_command(b"print('safe')", timeout_seconds=120)
        self.assertIn("60s", shlex.split(default))
        self.assertIn("120s", shlex.split(extended))
        for timeout in (True, 0, -1, 121, 2.5, "120"):
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                runner().build_command(b"print('safe')", timeout_seconds=timeout)

    def test_missing_operator_phrase_never_sends_a_command(self):
        argv = [
            "initialize_tts_allowance",
            "--instance-id",
            "i-" + "a" * 17,
            "--revision",
            "a" * 40,
            "--characters",
            "1000000",
            "--period",
            PERIOD,
            "--authorization",
            "not_authorized",
        ]
        with (
            patch.object(sys, "argv", argv),
            patch.object(runner(), "run") as remote,
            patch.object(runner(), "install_signal_handlers"),
            redirect_stdout(io.StringIO()) as log,
        ):
            self.assertEqual(runner().main(), 1)
        remote.assert_not_called()
        self.assertEqual(json.loads(log.getvalue())["transportCode"], "invalid_request")


class ResultTests(unittest.TestCase):
    def verified(self, value):
        return runner().verified(value, DIGEST, 1000000, PERIOD, OPERATION)

    def test_success_requires_matching_request_and_stable_container(self):
        self.assertTrue(self.verified(runner().sanitize(output(), "")))
        for field, changed in (
            ("operationId", "f" * 32),
            ("period", "2000-01"),
            ("requestedCharacters", 999999),
            ("cloudUsageVerified", True),
            ("allowanceSource", "cloud_usage_confirmed"),
            ("ok", False),
            ("applied", False),
            ("mutationState", "unknown"),
        ):
            value = report()
            value[field] = changed
            with self.subTest(field=field):
                self.assertFalse(self.verified(runner().sanitize(output(value), "")))
        for field, changed in (
            ("probeSha256", "f" * 64),
            ("status", "failed"),
            ("code", "runtime_changed_during_check"),
            ("containerId", ""),
            ("imageId", ""),
        ):
            with self.subTest(field=field):
                self.assertFalse(
                    self.verified(runner().sanitize(output(completion={field: changed}), ""))
                )

    def test_bad_or_unverified_counts_cannot_be_success(self):
        for snapshot in (
            {},
            {"limit": True, "used": 0, "remaining": 1},
            {"limit": 1000000, "used": -1, "remaining": 1000000},
            {"limit": 1000000, "used": 1, "remaining": 1000000},
        ):
            value = report()
            value["snapshot"] = snapshot
            with self.subTest(snapshot=snapshot):
                self.assertFalse(self.verified(runner().sanitize(output(value), "")))

    def test_raw_error_values_and_unknown_fields_are_filtered(self):
        secret = "secret-token-never-print"
        value = report()
        value.update(project=secret, key=secret, exception=secret)
        value["snapshot"]["key"] = secret
        safe = runner().sanitize(output(value) + "\n" + secret, secret)
        self.assertNotIn(secret, json.dumps(safe))
        self.assertTrue(safe["stderrPresent"])
        self.assertTrue(self.verified(safe))
        for code in (secret, [], {}, None):
            value = report()
            value["code"] = code
            with self.subTest(code=code):
                safe = runner().sanitize(output(value), secret)
                self.assertFalse(self.verified(safe))
                self.assertNotIn(secret, json.dumps(safe))
        self.assertIsNone(runner().sanitize("x" * 16001, secret)["report"])


class WorkflowTests(unittest.TestCase):
    def test_only_develop_manual_job_can_write_and_uses_deployment_lock(self):
        source = (ROOT / ".github/workflows/initialize-tts-allowance.yml").read_text("utf-8")
        validation, operation = source.split("  initialize:", 1)
        self.assertIn("pull_request:", validation)
        self.assertIn("unittest discover", validation)
        self.assertNotIn("id-token: write", validation)
        self.assertNotIn("configure-aws-credentials", validation)
        self.assertIn("github.event_name == 'workflow_dispatch'", operation)
        self.assertIn("github.ref == 'refs/heads/develop'", operation)
        self.assertIn("group: devon-production-deploy", operation)
        self.assertIn("cancel-in-progress: false", operation)
        deploy = (ROOT / ".github/workflows/deploy-ec2.yml").read_text("utf-8")
        self.assertIn("group: devon-production-deploy", deploy)

    def test_amount_has_no_default_and_inputs_are_quoted_environment_values(self):
        source = (ROOT / ".github/workflows/initialize-tts-allowance.yml").read_text("utf-8")
        amount = source.split("      characters:", 1)[1].split("      period:", 1)[0]
        self.assertIn("required: true", amount)
        self.assertNotIn("default:", amount)
        run = source.split("        run: >-", 1)[1].split("      - name:", 1)[0]
        self.assertNotIn("${{", run)
        self.assertIn('--characters "$REQUESTED_CHARACTERS"', run)
        self.assertIn('--period "$EXPECTED_PERIOD"', run)
        self.assertIn('--authorization "$OPERATOR_AUTHORIZATION"', run)
        self.assertIn("--revision", run)


if __name__ == "__main__":
    unittest.main()
