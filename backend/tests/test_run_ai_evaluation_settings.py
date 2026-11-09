"""manifest 없는 Judge 교정은 전역 호출 제한을 인자 없이 읽는다."""

from argparse import Namespace
from pathlib import Path

import pytest

from app.core.config import Settings
from scripts import run_ai_evaluation as cli

CASES = Path(__file__).resolve().parents[2] / "ai" / "evals"


@pytest.mark.asyncio
async def test_calibration_without_manifest_uses_settings_limits(monkeypatch):
    settings = Settings(
        _env_file=None,
        openai_api_key="test-key",
        llm_timeout_seconds=5,
        llm_max_output_tokens=100,
        llm_max_input_bytes=10000,
        llm_max_response_bytes=10000,
    )
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    settings_type = type(settings.require_llm())
    original_call_limits = settings_type.call_limits
    calls = []

    def global_limits_only(current):
        # manifest가 없는 분기는 작업별 제한 API에 의존하지 않아야 한다.
        calls.append(current)
        return original_call_limits(current)

    monkeypatch.setattr(settings_type, "call_limits", global_limits_only)

    async def fake_run_cases(cases, executor, *, metadata, **kwargs):
        return {"summary": {}, "metadata": metadata}

    monkeypatch.setattr(cli, "run_cases", fake_run_cases)
    args = Namespace(
        cases=CASES,
        manifest=None,
        output=Path("unused.json"),
        split="all",
        approved_only=False,
        execute=False,
        rejudge_results=None,
        calibrate_judge_only=True,
        dry_run=False,
        max_model_attempts=None,
        llm_judge=True,
        max_judge_attempts=1,
        diagnostic_judge=False,
        env_file=None,
        judge_prompt=None,
        judge_prompt_version=None,
        grader=None,
    )
    result = await cli.execute(args)
    assert len(calls) == 1
    assert result["judge_budget"]["maximum"] == 1
    assert result["metadata"]["limits"]["timeout_seconds"] == 5
