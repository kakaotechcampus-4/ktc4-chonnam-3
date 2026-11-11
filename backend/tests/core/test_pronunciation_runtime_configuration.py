"""등록된 발음 작업의 설정 경계와 비밀값 없는 배포 진단을 확인한다."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from devon_ai.contracts import PromptSpec
from pydantic import ValidationError

from app.core.config import LLMSettings, Settings
from app.integrations.tts.pronunciation import SpeechFragment
from app.llm_tasks import question_pronunciation
from scripts import configure_ai_runtime


def test_every_runtime_recipe_task_accepts_a_timeout_override():
    recipe = Path(__file__).resolve().parents[3] / "ai/prompts/runtime-prompts.json"
    tasks = json.loads(recipe.read_text(encoding="utf-8"))
    configured = Settings(_env_file=None, llm_task_timeouts={task: 2 for task in tasks})
    assert set(configured.llm_task_timeouts) == set(tasks)


def test_unknown_timeout_task_is_still_rejected():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, llm_task_timeouts={"unknown_runtime_task": 2})


@pytest.mark.parametrize("configured_seconds", [1.5, 5.0, 60.0])
async def test_pronunciation_override_keeps_request_local_five_second_cap(
    monkeypatch, configured_seconds
):
    configured = Settings(
        _env_file=None,
        openai_api_key="fixture-key",
        llm_timeout_seconds=60,
        llm_max_output_tokens=2048,
        llm_max_input_bytes=65536,
        llm_max_response_bytes=65536,
        llm_task_timeouts={"question_pronunciation": configured_seconds},
    )
    captured = []

    async def model(request, validator, **kwargs):
        captured.append(request)
        return SimpleNamespace(data=validator({"f1": "픽스처"}), failure=None)

    monkeypatch.setattr(question_pronunciation, "call_model", model)
    result = await question_pronunciation.pronounce_fragments(
        configured.require_llm(),
        PromptSpec("question_pronunciation", "question_pronunciation_v2", "fixture", "fixture"),
        (SpeechFragment("fixture", "term", "발음 대상"),),
    )
    assert result == ("픽스처",)
    assert len(captured) == 1
    assert captured[0].limits.timeout_seconds == min(configured_seconds, 5.0)
    assert captured[0].max_attempts == 1
    assert configured.llm_timeout_seconds == 60


def test_runtime_diagnostic_names_invalid_field_without_its_input(monkeypatch, tmp_path, capsys):
    def invalid_settings(**kwargs):
        return LLMSettings(
            openai_api_key="fixture-secret-key-must-not-appear",
            llm_default_model="fixture",
            llm_timeout_seconds="private-invalid-timeout",
            llm_max_output_tokens=2048,
            llm_max_input_bytes=65536,
            llm_max_response_bytes=65536,
        )

    monkeypatch.setattr(configure_ai_runtime, "Settings", invalid_settings)
    assert configure_ai_runtime.main(["--output", str(tmp_path / "manifest.json")]) == 1
    stderr = capsys.readouterr().err
    assert "llm_timeout_seconds" in stderr
    assert "private-invalid-timeout" not in stderr
    assert "fixture-secret-key-must-not-appear" not in stderr
