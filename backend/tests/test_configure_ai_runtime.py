"""실행 프롬프트 설정과 평가 manifest가 동일한 본문·모델을 사용하는지 검사한다."""

from pathlib import Path

import pytest
from devon_ai import contracts as c

from scripts.configure_ai_runtime import build_manifest
from scripts.run_ai_evaluation import load_manifest


def test_manifest_resolves_all_runtime_tasks_without_provider_or_database(tmp_path):
    import json

    output = tmp_path / "manifest.json"
    limits = c.CallLimits(30, 4096, 65536, 262144, reasoning_effort="low")
    manifest = build_manifest("configured-model", limits, output)
    output.write_text(json.dumps(manifest), encoding="utf-8")
    prompts, loaded_limits, metadata = load_manifest(output)
    from scripts.seed_prompt_versions import _validate_registration

    _validate_registration(list(prompts.values()))
    assert set(prompts) == {
        "repo_shallow",
        "repo_deep",
        "domain_category",
        "doc_claims",
        "director",
        "answer_analysis",
        "report",
        "report_score",
        "profile_summary",
        "claim_code",
        "jd_extract_image",
    }
    assert {item.model for item in prompts.values()} == {"configured-model"}
    assert prompts["director"].version == "director_v17"
    assert prompts["answer_analysis"].version == "answer_analysis_v7"
    assert prompts["report"].version == "report_v4"
    assert prompts["repo_shallow"].version == "repo_shallow_v3"
    assert prompts["doc_claims"].version == "doc_claims_v2"
    assert all(item.template.strip() for item in prompts.values())
    assert loaded_limits == limits
    assert len(metadata["prompts"]) == 11


@pytest.mark.parametrize("deployment", [None, "director-20261111"])
def test_release_manifest_keeps_current_consumers_and_one_deployment_suffix(tmp_path, deployment):
    import json

    from devon_ai.agents.director.capabilities import prompt_capabilities
    from devon_ai.agents.director.review import review_schema_version
    from devon_ai.agents.director.runtime import operation_prompts
    from devon_ai.prompt_versions import base_prompt_version

    from app.llm_tasks.runtime_capabilities import validate_runtime_prompts
    from scripts.seed_prompt_versions import _validate_registration

    output = tmp_path / "runtime.json"
    manifest = build_manifest(
        "configured-model", c.CallLimits(30, 4096, 65536, 262144), output, deployment=deployment
    )
    output.write_text(json.dumps(manifest), encoding="utf-8")
    prompts, _, _ = load_manifest(output)
    validate_runtime_prompts(list(prompts.values()))
    _validate_registration(list(prompts.values()))
    root = Path(__file__).resolve().parents[2] / "ai/prompts"
    expected = {
        "director": ("director_v17", "director-runtime-v17-semantic-fit.md"),
        "answer_analysis": (
            "answer_analysis_v7",
            "answer-analysis-runtime-v7-claim-contribution-scope.md",
        ),
        "report": ("report_v4", "report-runtime-v4.md"),
    }
    for task, (version, filename) in expected.items():
        prompt = prompts[task]
        assert base_prompt_version(prompt.version) == version
        assert prompt.version == version + ("@" + deployment if deployment else "")
        assert prompt.template == (root / filename).read_text(encoding="utf-8")
    assert all(
        prompt.version.count("@") == int(deployment is not None) for prompt in prompts.values()
    )
    assert prompt_capabilities(prompts["director"].version).source_bound_contract
    assert review_schema_version(prompts["director"].version) == "director-review.v3"
    plan, review = operation_prompts(prompts["director"])
    assert plan.template != review.template


def test_release_keeps_older_prompt_consumers_available():
    from app.llm_tasks.runtime_capabilities import validate_runtime_prompts
    from scripts.seed_prompt_versions import _validate_registration

    root = Path(__file__).resolve().parents[2] / "ai/prompts"
    prompts = [
        c.PromptSpec(
            task, version, "configured-model", (root / filename).read_text(encoding="utf-8")
        )
        for task, version, filename in (
            ("director", "director_v8@previous", "director-runtime-v8.md"),
            ("answer_analysis", "answer_analysis_v6@previous", "answer-analysis-runtime-v6.md"),
            ("report", "report_v3@previous", "report-runtime-v3.md"),
        )
    ]
    validate_runtime_prompts(prompts)
    _validate_registration(prompts)


async def test_release_rejects_old_installed_consumer_before_opening_database(
    tmp_path, monkeypatch
):
    from types import SimpleNamespace

    from app.llm_tasks import runtime_capabilities
    from scripts import configure_ai_runtime as runtime

    output = tmp_path / "runtime.json"
    manifest = build_manifest("configured-model", c.CallLimits(30, 4096, 65536, 262144), output)
    original_import = runtime_capabilities.import_module

    def old_director(name):
        if name == "devon_ai.agents.director.runtime":
            return SimpleNamespace(SUPPORTED_PROMPT_VERSIONS={"director_v8"})
        return original_import(name)

    def database_must_not_open(*args, **kwargs):
        raise AssertionError("unsupported consumers must be rejected before database access")

    monkeypatch.setattr(runtime_capabilities, "import_module", old_director)
    monkeypatch.setattr(runtime, "create_async_engine", database_must_not_open)
    with pytest.raises(c.ContractError, match="runtime prompt is not supported"):
        await runtime.apply_manifest(manifest, output, "postgresql+asyncpg://offline.invalid/test")


def test_v13_operation_policy_is_checked_before_registration():
    from app.llm_tasks.runtime_capabilities import validate_runtime_prompts

    template = (
        Path(__file__).resolve().parents[2] / "ai/prompts/director-runtime-v13-phase-focused-3.md"
    ).read_text(encoding="utf-8")
    valid = c.PromptSpec("director", "director_v13@phase-focused-3", "configured-model", template)
    validate_runtime_prompts([valid])
    incomplete = c.PromptSpec(
        valid.task_name, valid.version, valid.model, template.split("## 독립 검토")[0]
    )
    with pytest.raises(c.ContractError, match="Director operation prompt sections"):
        validate_runtime_prompts([incomplete])


def test_deployment_identity_preserves_template_with_new_immutable_model_version(tmp_path):
    limits = c.CallLimits(30, 4096, 65536, 262144)
    plain = build_manifest("old-model", limits, tmp_path / "plain.json")
    deployed = build_manifest("new-model", limits, tmp_path / "new.json", deployment="sol-20261107")
    assert [p["task_name"] for p in plain["prompts"]] == [
        p["task_name"] for p in deployed["prompts"]
    ]
    for old, new in zip(plain["prompts"], deployed["prompts"], strict=True):
        assert new["version"] == old["version"] + "@sol-20261107"
        assert new["template_path"] == old["template_path"]
        assert new["model"] == "new-model"


def test_manifest_write_failure_happens_before_any_database_activation(tmp_path, monkeypatch):
    from app.core.config import Settings
    from scripts import configure_ai_runtime as runtime

    settings = Settings(
        _env_file=None,
        openai_api_key="test",
        llm_default_model="configured-model",
        llm_timeout_seconds=30,
        llm_max_output_tokens=2000,
        llm_max_input_bytes=262144,
        llm_max_response_bytes=1048576,
    )
    monkeypatch.setattr(runtime, "Settings", lambda **kwargs: settings)
    called = []

    async def apply(*args):
        called.append(args)

    monkeypatch.setattr(runtime, "apply_manifest", apply)
    blocked = tmp_path / "blocked"
    blocked.write_text("file", encoding="utf-8")
    assert runtime.main(["--output", str(blocked / "manifest.json"), "--apply"]) == 1
    assert called == []
