"""구형 소비자의 존재만으로 최신 recipe를 활성화하지 않는다."""

from types import SimpleNamespace

import pytest
from devon_ai import contracts as c

from scripts import configure_ai_runtime as runtime


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("task", "version", "supported"),
    [
        ("director", "director_v8", {"director_v1", "director_v2"}),
        ("answer_analysis", "answer_analysis_v6", {"answer_analysis_v1"}),
    ],
)
async def test_legacy_consumer_cannot_activate_new_recipe_before_database_open(
    monkeypatch, tmp_path, task, version, supported
):
    import app.llm_tasks.runtime_capabilities as capability

    (tmp_path / "prompt.md").write_text("fixture body", encoding="utf-8")
    manifest = {
        "prompts": [
            {
                "task_name": task,
                "version": version + "@deployment",
                "model": "fixture",
                "template_path": "prompt.md",
            }
        ]
    }
    opened = []
    monkeypatch.setattr(
        capability,
        "import_module",
        lambda _: SimpleNamespace(SUPPORTED_PROMPT_VERSIONS=frozenset(supported)),
    )
    monkeypatch.setattr(runtime, "create_async_engine", lambda *args: opened.append(args))
    with pytest.raises(c.ContractError):
        await runtime.apply_manifest(
            manifest, tmp_path / "manifest.json", "postgresql+asyncpg://invalid"
        )
    assert opened == []
