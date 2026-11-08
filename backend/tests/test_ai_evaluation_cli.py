"""명시적 Judge 실행·교정 모드와 서비스 사례 binding을 비용 없이 검증한다."""

import argparse
import hashlib
import json
import subprocess
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from scripts import run_ai_evaluation as cli
from tests.agents.director_helpers import response
from tests.test_ai_model_judge import llm

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "failure",
    [
        FileNotFoundError("private-endpoint-fixture"),
        PermissionError("private-token-fixture"),
        subprocess.CalledProcessError(128, ["git"], stderr="private-stderr-fixture"),
    ],
    ids=["missing", "not-executable", "not-a-checkout"],
)
def test_source_metadata_without_git_preserves_fingerprints_without_private_errors(
    monkeypatch, tmp_path, failure
):
    source = tmp_path / "backend/app/fixture.py"
    source.parent.mkdir(parents=True)
    source.write_text("fixture = True\n", encoding="utf-8")
    monkeypatch.setattr(cli, "REPO_ROOT", tmp_path)

    def unavailable(*args, **kwargs):
        raise failure

    monkeypatch.setattr(cli.subprocess, "run", unavailable)
    result = cli.source_metadata()
    assert result["source_revision"] is None
    assert result["source_revision_status"] == "unavailable"
    assert result["source_revision_error"] == "git_unavailable"
    assert result["source_files"] == {
        "backend/app/fixture.py": hashlib.sha256(source.read_bytes()).hexdigest()
    }
    assert len(result["working_source_sha256"]) == 64
    assert "private-" not in json.dumps(result)


def test_source_metadata_records_a_real_revision_when_git_is_available(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "REPO_ROOT", tmp_path)
    revision = "a" * 40
    monkeypatch.setattr(
        cli.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(stdout=revision + "\n")
    )
    result = cli.source_metadata()
    assert result["source_revision"] == revision
    assert result["source_revision_status"] == "available"
    assert result["source_revision_error"] is None


def args(**updates):
    values = dict(
        execute=False,
        grader=None,
        cases=ROOT / "ai/evals",
        manifest=None,
        split="dev",
        approved_only=True,
        max_model_attempts=None,
        llm_judge=False,
        max_judge_attempts=None,
        calibrate_judge_only=False,
        env_file=None,
        judge_prompt=None,
        diagnostic_judge=False,
    )
    return argparse.Namespace(**{**values, **updates})


@pytest.mark.parametrize(
    "updates",
    [
        {"diagnostic_judge": True},
        {"diagnostic_judge": True, "execute": True, "max_model_attempts": 1},
        {
            "diagnostic_judge": True,
            "llm_judge": True,
            "max_judge_attempts": 1,
            "calibrate_judge_only": True,
        },
    ],
)
async def test_diagnostic_judge_requires_explicit_service_execution_and_a_grader(
    updates, monkeypatch
):
    def forbidden_settings(*args, **kwargs):
        raise AssertionError("invalid diagnostic mode must not load provider settings")

    monkeypatch.setattr(cli, "get_settings", forbidden_settings)
    monkeypatch.setattr(cli, "Settings", forbidden_settings)
    with pytest.raises(ValueError, match="diagnostic"):
        await cli.execute(args(**updates))


async def test_typed_dataset_dry_run_records_fingerprints_and_automatic_completion(monkeypatch):
    def forbidden_settings(*args, **kwargs):
        raise AssertionError("dry run must not load actual provider settings")

    monkeypatch.setattr(cli, "get_settings", forbidden_settings)
    monkeypatch.setattr(cli, "Settings", forbidden_settings)
    dataset = ROOT / "ai/evals/service_regression"
    result = await cli.execute(
        args(cases=dataset, manifest=dataset / "manifest.json", split="all", approved_only=False)
    )
    assert result["summary"]["statuses"] == {"validated_only": 32}
    assert result["summary"]["automatic_checks"]["input_contract"]["status"] == "passed"
    assert result["summary"]["automatic_checks"]["service_execution"]["status"] == "not_executed"
    assert result["summary"]["human_review_status"] == "deferred"
    assert result["summary"]["quality_denominator"] == 0
    snapshot = result["metadata"]["dataset"]
    assert len(snapshot["sha256"]) == 64
    assert "binding-manifest.json" in snapshot["files"]
    assert len(snapshot["files"]) == 65


@pytest.mark.parametrize(
    "updates,reason",
    [
        ({"llm_judge": True, "max_judge_attempts": 1}, "explicit execution"),
        ({"llm_judge": True, "calibrate_judge_only": True}, "max-judge-attempts"),
        ({"calibrate_judge_only": True}, "llm-judge"),
    ],
)
async def test_judge_requires_explicit_mode_and_its_own_budget(updates, reason):
    with pytest.raises(ValueError, match=reason):
        await cli.execute(args(**updates))


@pytest.mark.parametrize("judge_version", [None, "evaluation-judge-v3"])
async def test_calibration_uses_only_reviewed_controls_and_preserves_missing_service_binding(
    monkeypatch, tmp_path, judge_version
):
    captured_env = []
    monkeypatch.setattr(
        cli,
        "Settings",
        lambda **kwargs: (
            captured_env.append(kwargs["_env_file"]) or SimpleNamespace(require_llm=llm)
        ),
        raising=False,
    )
    sent = []

    def handle(request):
        sent.append(request)
        return response(
            {"verdict": "ambiguous", "reason_summary": "맥락 한계가 있다", "criterion_results": []}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        actual = cli.call_model

        async def call(request, validator, **kwargs):
            kwargs["http_client"] = http
            return await actual(request, validator, **kwargs)

        monkeypatch.setattr(cli, "call_model", call)
        result = await cli.execute(
            args(
                llm_judge=True,
                max_judge_attempts=1,
                calibrate_judge_only=True,
                env_file=tmp_path / "fixture.env",
                judge_prompt=ROOT / "ai/prompts/evaluation-judge-v3.md" if judge_version else None,
                judge_prompt_version=judge_version,
            )
        )
    assert captured_env == [tmp_path / "fixture.env"]
    assert len(sent) == 1 and result["metadata"]["mode"] == "judge_calibration"
    assert all(
        row["status"] == "not_executed" and row["error_code"] == "explicit_service_input_required"
        for row in result["cases"]
    )
    assert (
        result["summary"]["quality_denominator"] == 0
        and result["summary"]["release_gate_passed"] is None
    )
    assert result["judge_budget"]["remaining"] == 0
    assert result["grader_controls"]["evaluated_cases"] == len(result["cases"])
    body = json.loads(sent[0].content)
    payload = json.loads(body["input"][0]["content"][0]["text"])
    assert set(payload) == {"rubric", "candidate_output", "source_context"}
    assert payload["source_context"]["schema_version"] == "judge-context.v1"
    assert result["metadata"]["grader"]["prompt_version"] == (
        judge_version or "evaluation-judge-v2"
    )
    assert "grader_controls" not in json.dumps(payload) and "reviewed_at" not in json.dumps(payload)
    assert "private-judge-fixture-key" not in json.dumps(result)


async def test_rejudge_refuses_changed_dataset_before_settings_or_http(monkeypatch, tmp_path):
    def forbidden(*args, **kwargs):
        raise AssertionError("invalid source must not read provider settings")

    monkeypatch.setattr(cli, "Settings", forbidden)
    monkeypatch.setattr(cli, "get_settings", forbidden)
    previous = tmp_path / "previous.json"
    previous.write_text(
        json.dumps({"metadata": {"dataset": {"sha256": "changed"}}}), encoding="utf-8"
    )
    dataset = ROOT / "ai/evals/service_regression"
    with pytest.raises(ValueError, match="dataset or binding manifest"):
        await cli.execute(
            args(
                cases=dataset,
                manifest=dataset / "manifest.json",
                rejudge_results=previous,
                llm_judge=True,
                max_judge_attempts=1,
            )
        )


async def test_rejudge_uses_only_saved_output_and_one_judge_without_service_factory(
    monkeypatch, tmp_path
):
    from eval_cases import load_cases
    from eval_runner import Execution, run_cases

    dataset = ROOT / "ai/evals/service_regression"
    case = load_cases(dataset)[0]
    bindings = cli._bindings([case])

    async def saved_executor(kind, payload):
        return Execution({"saved": "candidate"})

