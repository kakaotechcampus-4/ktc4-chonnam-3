"""실행 프롬프트 설정과 평가 manifest가 동일한 본문·모델을 사용하는지 검사한다."""

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
        "question_pronunciation",
    }
    assert {item.model for item in prompts.values()} == {"configured-model"}
    assert prompts["director"].version == "director_v8"
    assert prompts["repo_shallow"].version == "repo_shallow_v3"
    assert prompts["doc_claims"].version == "doc_claims_v2"
    assert all(item.template.strip() for item in prompts.values())
    assert loaded_limits == limits
    assert len(metadata["prompts"]) == 12
    assert prompts["question_pronunciation"].model == "configured-model"


def test_deployment_identity_preserves_template_with_new_immutable_model_version(tmp_path):
    limits = c.CallLimits(30, 4096, 65536, 262144)
    plain = build_manifest("old-model", limits, tmp_path / "plain.json")
    deployed = build_manifest("new-model", limits, tmp_path / "new.json", deployment="sol-20261107")
    assert [p["task_name"] for p in plain["prompts"]] == [
        p["task_name"] for p in deployed["prompts"]
    ]
    for old, new in zip(plain["prompts"], deployed["prompts"], strict=True):
        if old["task_name"] == "question_pronunciation":
            assert old["version"].startswith("question_pronunciation_v2@")
            assert new["version"].startswith("question_pronunciation_v2@sol-20261107-")
        else:
            assert new["version"] == old["version"] + "@sol-20261107"
        assert new["template_path"] == old["template_path"]
        assert new["model"] == "new-model"


def test_pronunciation_model_override_changes_only_its_task(tmp_path):
    from app.llm_tasks.runtime_capabilities import validate_runtime_prompts
    from scripts.seed_prompt_versions import _validate_registration

    limits = c.CallLimits(30, 4096, 65536, 262144)
    output = tmp_path / "manifest.json"
    default = build_manifest("director-model", limits, output)
    overridden = build_manifest(
        "director-model", limits, output, pronunciation_model="voice-model-a"
    )
    changed = build_manifest("director-model", limits, output, pronunciation_model="voice-model-b")
    assert overridden["prompts"][:-1] == changed["prompts"][:-1] == default["prompts"][:-1]
    assert default["prompts"][-1]["task_name"] == "question_pronunciation"
    assert default["prompts"][-1]["model"] == "director-model"

    voice_a, voice_b = overridden["prompts"][-1], changed["prompts"][-1]
    assert voice_a["task_name"] == voice_b["task_name"] == "question_pronunciation"
    assert voice_a["model"] == "voice-model-a" and voice_b["model"] == "voice-model-b"
    assert voice_a["version"] != voice_b["version"]
    prompts = [
        c.PromptSpec(voice["task_name"], voice["version"], voice["model"], "reviewed body")
        for voice in (voice_a, voice_b)
    ]
    for prompt in prompts:
        validate_runtime_prompts([prompt])
        _validate_registration([prompt])


def test_runtime_uses_selected_luna_for_pronunciation_without_an_override(tmp_path, monkeypatch):
    import json

    from app.core.config import Settings
    from scripts import configure_ai_runtime as runtime

    settings = Settings(
        _env_file=None,
        openai_api_key="fixture-key",
        llm_default_model="legacy-model",
        openai_model="gpt-6-luna",
        llm_timeout_seconds=50,
        llm_max_output_tokens=4096,
        llm_max_input_bytes=65536,
        llm_max_response_bytes=65536,
        llm_reasoning_effort="xhigh",
    )
    monkeypatch.setattr(runtime, "Settings", lambda **kwargs: settings)
    output = tmp_path / "runtime.json"

    assert runtime.main(["--output", str(output)]) == 0

    manifest = json.loads(output.read_text(encoding="utf-8"))
    pronunciation = next(
        prompt for prompt in manifest["prompts"] if prompt["task_name"] == "question_pronunciation"
    )
    assert pronunciation["model"] == "gpt-6-luna"
    assert manifest["limits"]["reasoning_effort"] == "xhigh"


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
