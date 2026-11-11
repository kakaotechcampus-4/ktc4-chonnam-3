"""유료 실행 전 검증·Luna 경계·원본 결과 보존을 검사한다."""

import json
from dataclasses import asdict

import pytest
from devon_ai import contracts as c

from scripts.run_director_study import execute, luna_factory, parser


def test_partial_cohort_uses_the_real_follow_up_policy_path():
    from devon_ai.agents.director.policy import with_follow_up_options
    from director_cases import build_cohort

    from scripts.ai_eval_bridge import prepare

    case = next(case for case in build_cohort().cases if case.case_id.endswith("-partial"))
    task, data = prepare(case.kind, case.model_input())
    assert task == "director"
    context = with_follow_up_options(data["context"], data["answer_analysis"])
    assert len(context.follow_up_options) == 1
    option = context.follow_up_options[0]
    assert option.parent_turn_id == context.current_turn_id
    assert option.missing_point_keys == ("failure",)


def manifest(tmp_path, model="gpt-6-luna"):
    template = tmp_path / "director.md"
    template.write_text("제공된 자료로 한 중심 목적의 질문을 생성한다.", encoding="utf-8")
    path = tmp_path / "manifest.json"
    path.write_text(
        json.dumps(
            {
                "prompts": [
                    {
                        "task_name": "director",
                        "version": "director_v8",
                        "model": model,
                        "template_path": "director.md",
                    }
                ],
                "limits": {
                    "timeout_seconds": 30,
                    "max_output_tokens": 1000,
                    "max_input_bytes": 262144,
                    "max_response_bytes": 1048576,
                },
            }
        ),
        encoding="utf-8",
    )
    return path


async def test_dry_run_validates_pilot_without_settings_or_provider(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("dry-run must not load secrets or call a provider")

    monkeypatch.setattr("scripts.run_director_study.get_settings", forbidden)
    output = tmp_path / "result.json"
    args = parser().parse_args(["--manifest", str(manifest(tmp_path)), "--output", str(output)])
    result = await execute(args)
    assert result["summary"]["statuses"] == {"validated_only": 12}
    assert result["metadata"]["study"]["source_groups"] == 12
    assert all(not row["attempts"] for row in result["cases"])
    assert result["metadata"]["study"]["model_api_calls"] == 0
    assert json.loads(output.read_text(encoding="utf-8"))["run_state"] == "completed"


async def test_non_luna_manifest_is_rejected_before_execution(tmp_path):
    args = parser().parse_args(
        [
            "--manifest",
            str(manifest(tmp_path, "gpt-6-sol")),
            "--output",
            str(tmp_path / "result.json"),
        ]
    )
    with pytest.raises(ValueError, match="Luna"):
        await execute(args)


async def test_live_requires_attempt_and_wall_budgets_before_settings(tmp_path):
    args = parser().parse_args(
        [
            "--manifest",
            str(manifest(tmp_path)),
            "--output",
            str(tmp_path / "result.json"),
            "--execute",
        ]
    )
    with pytest.raises(ValueError, match="budget"):
        await execute(args)


async def test_live_rejects_non_luna_environment_before_any_request(tmp_path, monkeypatch):
    from types import SimpleNamespace

    configured = SimpleNamespace(
        llm_default_model="gpt-6-sol",
        call_limits=lambda task: c.CallLimits(30, 1000, 262144, 1048576),
    )
    monkeypatch.setattr(
        "scripts.run_director_study.get_settings",
        lambda: SimpleNamespace(require_llm=lambda: configured),
    )
    output = tmp_path / "result.json"
    args = parser().parse_args(
        [
            "--manifest",
            str(manifest(tmp_path)),
            "--output",
            str(output),
            "--execute",
            "--max-model-attempts",
            "24",
            "--max-wall-seconds",
            "1800",
        ]
    )
    with pytest.raises(ValueError, match="Luna"):
        await execute(args)
    assert not output.exists()


async def test_luna_guard_rejects_wrong_response_model_and_keeps_attempt_record():
    limits = c.CallLimits(30, 1000, 262144, 1048576)
    prompt = c.PromptSpec("director", "director_v8", "gpt-6-luna", "template")
    request = c.ModelRequest(prompt, {}, "output", "1", {}, limits, max_attempts=1)

    def factory():
        async def invoke(request, validator):
            attempt = c.AttemptMetadata(1, "fixture", "gpt-6-sol", "director_v8", "1", 1, 1, 1)
            return c.ModelResult({}, None, (attempt,))

        return invoke

    result = await luna_factory(factory, limits)()(request, lambda value: value)
    assert result.failure.error_code == "director_study_model_mismatch"
    assert asdict(result.attempts[0])["model"] == "gpt-6-sol"


async def test_luna_guard_rejects_changed_settings_without_a_call():
    limits = c.CallLimits(30, 1000, 262144, 1048576, reasoning_effort="xhigh")
    changed = c.CallLimits(30, 1000, 262144, 1048576, reasoning_effort="medium")
    prompt = c.PromptSpec("director", "director_v8", "gpt-6-luna", "template")
    request = c.ModelRequest(prompt, {}, "output", "1", {}, changed, max_attempts=1)

    def forbidden():
        raise AssertionError("changed settings must fail before provider factory")

    result = await luna_factory(forbidden, limits)()(request, lambda value: value)
    assert result.failure.error_code == "director_study_settings_mismatch"
    assert result.attempts == ()


async def test_luna_stage_record_preserves_review_failure(tmp_path):
    from app.integrations.execution_ledger import ExecutionLedger, execution_scope

    limits = c.CallLimits(30, 1000, 262144, 1048576)
    prompt = c.PromptSpec("director", "director_v8", "gpt-6-luna", "template")
    request = c.ModelRequest(prompt, {"operation": "review"}, "output", "1", {}, limits)

    def factory():
        async def invoke(request, validator):
            return c.ModelResult(None, c.CallFailure("semantic", "rejected", "rejected"), ())

        return invoke

    ledger = ExecutionLedger(tmp_path / "ledger.sqlite3")
    with execution_scope(ledger, run_id="run", entrypoint="test"):
        result = await luna_factory(factory, limits)()(request, lambda value: value)
    assert result.failure.error_code == "rejected"
    assert len(ledger.records()) == 1
    record = ledger.records()[0]
    assert record.operation == "director.review"
    assert record.status == "failed" and record.error_code == "rejected"
    assert record.elapsed_seconds is not None
