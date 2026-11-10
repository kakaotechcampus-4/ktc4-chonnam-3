"""미설치 소비자를 DB 활성화 전에 거절한다."""

import json
from types import SimpleNamespace

import pytest
from devon_ai import contracts as c

from scripts import configure_ai_runtime as runtime


def test_all_recipe_entries_have_installed_consumers():
    from app.llm_tasks.runtime_capabilities import validate_runtime_prompts

    recipe = json.loads((runtime.PROMPT_ROOT / "runtime-prompts.json").read_text(encoding="utf-8"))
    prompts = [
        c.PromptSpec(task, item["version"] + "@review", "fixture", "body")
        for task, item in recipe.items()
    ]
    validate_runtime_prompts(prompts)
    assert all(item.version.endswith("@review") for item in prompts)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["missing", "unsupported"])
async def test_activation_rejects_incomplete_installation_before_opening_database(
    monkeypatch, tmp_path, kind
):
    import app.llm_tasks.runtime_capabilities as capability

    template = tmp_path / "prompt.md"
    template.write_text("body", encoding="utf-8")
    manifest = {
        "prompts": [
            {
                "task_name": "director",
                "version": "director_v8@review",
                "model": "fixture",
                "template_path": template.name,
            }
        ]
    }
    opened = []

    def load(name):
        if kind == "missing":
            raise ModuleNotFoundError(name)
        return SimpleNamespace(SUPPORTED_PROMPT_VERSIONS=frozenset({"director_v1"}))

    monkeypatch.setattr(capability, "import_module", load)
    monkeypatch.setattr(runtime, "create_async_engine", lambda *args: opened.append(args))
    with pytest.raises(c.ContractError):
        await runtime.apply_manifest(
            manifest, tmp_path / "manifest.json", "postgresql+asyncpg://invalid"
        )
    assert opened == []


def test_unknown_task_cannot_claim_a_consumer():
    from app.llm_tasks.runtime_capabilities import validate_runtime_prompts

    with pytest.raises(c.ContractError):
        validate_runtime_prompts([c.PromptSpec("uninstalled", "uninstalled_v1", "fixture", "body")])
