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
