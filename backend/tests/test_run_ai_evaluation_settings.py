"""manifest 없이 Judge 교정을 실행할 때 설정의 제한값을 인자 없이 읽는지 검사한다."""

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
    assert result["judge_budget"]["maximum"] == 1
    assert result["metadata"]["limits"]["timeout_seconds"] == 5
