"""배포 준비의 DB·프롬프트 순서와 등록 실패 시 기동 차단을 외부 호출 없이 확인한다."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]


def test_api_and_worker_require_the_same_successfully_registered_runtime():
    services = yaml.safe_load((ROOT / "compose.deploy.yaml").read_text("utf-8"))["services"]
    registration = services["runtime-prompts"]
    assert registration["command"] == [
        "python",
        "-m",
        "scripts.configure_ai_runtime",
        "--output",
        "/tmp/ai-runtime.json",
        "--apply",
    ]
    assert registration["env_file"] == services["api"]["env_file"] == services["worker"]["env_file"]
    assert registration["depends_on"]["migrate"]["condition"] == "service_completed_successfully"
    for consumer in ("api", "worker"):
        assert services[consumer]["depends_on"]["runtime-prompts"]["condition"] == (
            "service_completed_successfully"
        )


@pytest.mark.parametrize("failure", ["migrate", "runtime-prompts", "none"])
def test_deploy_stops_before_starting_consumers_when_bootstrap_fails(tmp_path, failure):
    if sys.platform == "win32":
        bash = Path("C:/Program Files/Git/bin/bash.exe")
        if not bash.exists():
            pytest.skip("Git Bash is required for the deployment shell regression on Windows")
    else:
        executable = shutil.which("bash")
        if executable is None:
            pytest.skip("bash is required for the deployment shell regression")
        bash = Path(executable)
    commands = tmp_path / "commands"
    commands.mkdir()
    trace = tmp_path / "trace.txt"
    docker = commands / "docker"
    docker.write_text(
        '#!/bin/sh\nprintf "%s\\n" "$*" >> "$DEPLOY_TEST_TRACE"\n'
        'case "$*" in\n'
        ' *"--force-recreate"*"--exit-code-from $DEPLOY_TEST_FAILURE "*) exit 9;;\n'
        "esac\nexit 0\n",
        encoding="utf-8",
    )
    docker.chmod(0o755)
    curl = commands / "curl"
    curl.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    curl.chmod(0o755)
    env = os.environ | {
        "PATH": str(commands) + os.pathsep + os.environ["PATH"],
        "DEPLOY_TEST_TRACE": trace.as_posix(),
        "DEPLOY_TEST_FAILURE": failure,
    }
    result = subprocess.run(
        [str(bash), str(ROOT / "ops/deploy.sh")], env=env, capture_output=True, timeout=20
    )
    events = trace.read_text("utf-8").splitlines()
    consumer_start = next(
        (i for i, item in enumerate(events) if "up -d --remove-orphans" in item), None
    )
    if failure != "none":
        assert result.returncode != 0
        assert consumer_start is None
    else:
        assert result.returncode == 0, result.stderr.decode(errors="replace")
        migrate = next(i for i, item in enumerate(events) if "--exit-code-from migrate " in item)
        register = next(
            i for i, item in enumerate(events) if "--exit-code-from runtime-prompts " in item
        )
        assert migrate < register < consumer_start
