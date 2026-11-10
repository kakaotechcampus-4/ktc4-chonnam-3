"""운영 접근 없이 TTS 진단의 전송·출력·배포 분리 경계를 검증한다."""

import ast
import asyncio
import base64
import importlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".github/scripts"))
REVISION = "a" * 40
CONTAINER = "b" * 64
IMAGE = "sha256:" + "c" * 64
DIGEST = "d" * 64
STARTED = "2026-11-10T12:32:00.000000000Z"


def runner():
    return importlib.import_module("diagnose_tts")


def output(*, ok=True):
    return "\n".join(
        json.dumps(value)
        for value in (
            {
                "schemaVersion": 1,
                "phase": "tts",
                "ok": ok,
                "checks": [
                    {"name": name, "status": "ready", "code": "ready", "details": {}}
                    for name in (
                        "provider",
                        "authentication",
                        "voices",
                        "budget_configuration",
                        "tts",
                        "redis",
                        "tts_budget",
                        "google_voice_catalog",
                    )
                ],
                "externalRead": {"googleVoiceCatalog": True, "synthesisRequests": 0},
            },
            {
                "schemaVersion": 1,
                "event": "tts_diagnostic",
                "status": "passed" if ok else "failed",
                "code": "ready" if ok else "tts_not_ready",
                "containerId": CONTAINER,
                "imageId": IMAGE,
                "startedAt": STARTED,
                "probeSha256": DIGEST,
            },
        )
    )


class WorkflowTests(unittest.TestCase):
    def test_github_only_changes_do_not_deploy_but_runtime_changes_do(self):
        source = (ROOT / ".github/workflows/deploy-ec2.yml").read_text("utf-8")
        self.assertIn("paths-ignore: ['.github/**']", source)
        self.assertIn("workflow_dispatch:", source)

        def ignored(path):
            return path.startswith(".github/")

        self.assertTrue(
            all(
                ignored(path)
                for path in (
                    ".github/workflows/deploy-ec2.yml",
                    ".github/workflows/diagnose-tts.yml",
                    ".github/scripts/tts_probe.py",
                    ".github/tests/test_tts_diagnostic.py",
                )
            )
        )
        for path in (
            "backend/app/main.py",
            "ai/src/devon_ai/contracts.py",
            "frontend/src/main.tsx",
            "ops/deploy.sh",
            "compose.deploy.yaml",
            "backend/Dockerfile",
            ".dockerignore",
        ):
            self.assertFalse(ignored(path))
        self.assertIn(".github", (ROOT / ".dockerignore").read_text("utf-8").splitlines())

    def test_pull_request_validation_has_no_aws_credentials(self):
        source = (ROOT / ".github/workflows/diagnose-tts.yml").read_text("utf-8")
        validation, diagnostic = source.split("  diagnose:", 1)
        self.assertIn("pull_request:", validation)
        self.assertIn("unittest discover", validation)
        self.assertNotIn("id-token: write", validation)
        self.assertNotIn("configure-aws-credentials", validation)
        self.assertIn("github.event_name == 'workflow_dispatch'", diagnostic)
        self.assertIn("github.ref == 'refs/heads/develop'", diagnostic)
        self.assertIn("id-token: write", diagnostic)


class RunnerTests(unittest.TestCase):
    def test_missing_or_multiple_api_containers_return_safe_failure_json(self):
        bash = shutil.which("bash")
        windows = Path("C:/Program Files/Git/bin/bash.exe")
        if windows.exists():
            bash = str(windows)
        if bash is None:
            self.skipTest("bash is required")
        command, _ = runner().build_command(b"raise RuntimeError('must not execute')\n")
        script = shlex.split(command)[-1]
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "docker"
            executable.write_text(
                '#!/bin/sh\nif [ "$MOCK_CONTAINER_COUNT" = 2 ]; then '
                'printf "%s\\n%s\\n" "$MOCK_CONTAINER" "$MOCK_OTHER"; fi\n',
                encoding="utf-8",
            )
            executable.chmod(0o755)
            for count in (0, 2):
                with self.subTest(count=count):
                    env = dict(
                        os.environ,
                        PATH=directory + os.pathsep + os.environ["PATH"],
                        MOCK_CONTAINER_COUNT=str(count),
                        MOCK_CONTAINER=CONTAINER,
                        MOCK_OTHER="e" * 64,
                    )
                    completed = subprocess.run(
                        [bash, "-c", script],
                        env=env,
                        capture_output=True,
                        text=True,
                        timeout=10,
                        check=False,
                    )
                    self.assertNotEqual(completed.returncode, 0)
                    value = json.loads(completed.stdout)
                    self.assertEqual(value["code"], "api_container_unavailable")
                    self.assertEqual(value["containerId"], "")

    def test_actual_successful_probe_report_passes_transport_verification(self):
        settings = SimpleNamespace(
            tts_provider="google_cloud",
            tts_access_token=None,
            tts_api_key=SimpleNamespace(get_secret_value=lambda: "private-key"),
            tts_voice_map={
                name: "ko-KR-Chirp3-HD-" + voice
                for name, voice in (
                    ("tech_lead", "Charon"),
                    ("domain_lead", "Kore"),
                    ("hr_manager", "Aoede"),
                )
            },
            tts_language_code="ko-KR",
            tts_monthly_character_limit=1000,
            tts_budget_project="unit",
            redis_url="redis://unit/15",
            require_tts=lambda: object(),
        )

        class Redis:
            @classmethod
            def from_url(cls, *_args, **_kwargs):
                return cls()

            async def ping(self):
                return True

            async def info(self, _section):
                return {"run_id": "epoch"}

            async def hmget(self, *_args):
                return [b"epoch", b"1000", b"10", b"0", b"0"]

            async def aclose(self):
                return None

        modules = {}
        for name in (
            "httpx",
            "redis",
            "redis.asyncio",
            "app",
            "app.core",
            "app.core.config",
            "app.features",
            "app.features.interview",
            "app.features.interview.tts_budget",
        ):
            modules[name] = ModuleType(name)
            modules[name].__path__ = []
        modules["redis.asyncio"].Redis = Redis
        modules["app.core.config"].get_settings = lambda: settings
        modules["app.features.interview.tts_budget"].RedisCharacterBudget = (
            lambda *_args, **_kwargs: SimpleNamespace(period="2026-11", key="unit-budget")
        )
        with patch.dict(sys.modules, modules):
            spec = importlib.util.spec_from_file_location(
                "tts_probe_contract", ROOT / ".github/scripts/tts_probe.py"
            )
            probe = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(probe)

            async def catalog(_settings):
                probe._catalog_attempted = True
                return {
                    "name": "google_voice_catalog",
                    "status": "ready",
                    "code": "voice_catalog_available",
                    "details": {"httpStatus": 200},
                }

            probe.catalog_check = catalog
            result = asyncio.run(probe.inspect_tts())
        self.assertTrue(result["ok"])
        self.assertNotIn("tts", {check["name"] for check in result["checks"]})
        safe = runner().sanitize(json.dumps(result) + "\n" + output().splitlines()[1], "")
        self.assertTrue(runner().verified(safe, DIGEST))

    def test_payload_uses_current_container_without_install_or_deploy(self):
        payload = b"print('trusted probe')\n"
        command, digest = runner().build_command(payload)
        self.assertRegex(digest, r"^[0-9a-f]{64}$")
        self.assertIn(base64.b64encode(payload).decode(), command)
        self.assertIn('docker exec -i "$container" python -B -', command)
        self.assertIn(".State.StartedAt", command)
        self.assertIn("before", command)
        self.assertIn("after", command)
        for forbidden in (
            "git checkout",
            "git fetch",
            "docker compose",
            "docker run",
            "seed_all",
            "initialize_tts_budget",
            "ops/diagnose.sh",
            "pip install",
        ):
            self.assertNotIn(forbidden, command)

    def test_generated_remote_shell_has_valid_syntax(self):
        bash = shutil.which("bash")
        windows = Path("C:/Program Files/Git/bin/bash.exe")
        if windows.exists():
            bash = str(windows)
        if bash is None:
            self.skipTest("bash is required")
        command, _ = runner().build_command(b"print('probe')\n")
        script = shlex.split(command)[-1]
        result = subprocess.run(
            [bash, "-n"],
            input=script,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_raw_secrets_and_unknown_fields_are_never_returned(self):
        secret = "private-secret"
        value = json.loads(output().splitlines()[0])
        value["checks"].append(
            {
                "name": secret,
                "status": "error",
                "code": secret,
                "details": {"key": secret},
            }
        )
        value["checks"][0]["details"] = {"remaining": 5, "key": secret}
        value["raw"] = secret
        safe = runner().sanitize(json.dumps(value) + "\n" + secret, secret)
        self.assertNotIn(secret, json.dumps(safe))
        self.assertFalse(safe["report"]["ok"])

    def test_success_requires_matching_payload_and_stable_container(self):
        module = runner()
        safe = module.sanitize(output(), "")
        self.assertTrue(module.verified(safe, DIGEST))
        self.assertFalse(module.verified(safe, "e" * 64))
        changed = json.loads(output().splitlines()[1])
        changed.update(status="failed", code="runtime_changed_during_check")
        safe = module.sanitize(output().splitlines()[0] + "\n" + json.dumps(changed), "")
        self.assertFalse(module.verified(safe, DIGEST))

    def test_probe_has_no_new_operations_or_write_dependency(self):
        source = (ROOT / ".github/scripts/tts_probe.py").read_text("utf-8")
        ast.parse(source)
        self.assertNotIn("app.operations", source)
        self.assertNotIn("synthesize(", source)
        self.assertNotIn(".reserve(", source)
        self.assertNotIn("initialize_budget(", source)
        self.assertNotIn('stream("POST"', source)
        requests = [
            node
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "stream"
        ]
        self.assertEqual([node.args[0].value for node in requests], ["GET"])


class TransportTests(unittest.TestCase):
    def test_elapsed_deadline_cancels_without_reading_or_resending(self):
        transport = importlib.import_module("ssm_transport")
        calls = []
        clock = iter([0, 200])

        def aws(arguments):
            calls.append(arguments)
            if "send-command" in arguments:
                return {"Command": {"CommandId": "00000000-0000-4000-8000-000000000000"}}
            return {"Status": "Cancelled"}

        result = transport.run(
            "i-00000000000000000",
            "trusted",
            lambda *_: {},
            lambda _: True,
            aws=aws,
            sleep=lambda _: None,
            now=lambda: next(clock),
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["transportCode"], "remote_timeout")
        self.assertTrue(result["cancellationConfirmed"])
        self.assertEqual(sum("send-command" in call for call in calls), 1)

    def test_success_and_initial_invocation_delay_never_resend(self):
        transport = importlib.import_module("ssm_transport")
        calls = []

        def aws(arguments):
            calls.append(arguments)
            if "send-command" in arguments:
                return {"Command": {"CommandId": "00000000-0000-4000-8000-000000000000"}}
            if len(calls) == 2:
                raise transport.InvocationPending
            return {
                "Status": "Success",
                "ResponseCode": 0,
                "StandardOutputContent": output(),
            }

        module = runner()
        result = transport.run(
            "i-00000000000000000",
            "trusted",
            module.sanitize,
            lambda value: module.verified(value, DIGEST),
            aws=aws,
            sleep=lambda _: None,
        )
        self.assertTrue(result["ok"])
        self.assertEqual(sum("send-command" in call for call in calls), 1)

    def test_error_cancels_remote_command_and_does_not_expose_exception(self):
        transport = importlib.import_module("ssm_transport")
        calls = []

        def aws(arguments):
            calls.append(arguments)
            if "send-command" in arguments:
                return {"Command": {"CommandId": "00000000-0000-4000-8000-000000000000"}}
            if "cancel-command" in arguments:
                return {}
            raise RuntimeError("private-secret")

        result = transport.run(
            "i-00000000000000000",
            "trusted",
            lambda *_: {},
            lambda _: True,
            aws=aws,
            sleep=lambda _: None,
        )
        self.assertFalse(result["ok"])
        self.assertTrue(any("cancel-command" in call for call in calls))
        self.assertNotIn("private-secret", json.dumps(result))

    def test_terminal_failure_never_becomes_success(self):
        transport = importlib.import_module("ssm_transport")
        for status in (
            "Failed",
            "Cancelled",
            "TimedOut",
            "Undeliverable",
            "Cancelling",
        ):
            with self.subTest(status=status):

                def aws(arguments, status=status):
                    if "send-command" in arguments:
                        return {"Command": {"CommandId": "00000000-0000-4000-8000-000000000000"}}
                    return {"Status": status, "ResponseCode": 0}

                result = transport.run(
                    "i-00000000000000000",
                    "trusted",
                    lambda *_: {},
                    lambda _: True,
                    aws=aws,
                    sleep=lambda _: None,
                )
                self.assertFalse(result["ok"])


if __name__ == "__main__":
    unittest.main()
