"""모든 평가 모드에서 잘못된 Judge 결과를 감사 가능한 기술 실패로 보존한다."""

import asyncio
import copy

import pytest
from async_grader import Judgment, call_grader
from eval_cases import Case
from eval_runner import Execution, rejudge_cases, run_cases


def fixture(status="approved"):
    return Case(
        "q-invalid",
        1,
        "question",
        "dev",
        "group",
        {"history": []},
        {
            "allowed": [],
            "forbidden": [],
            "grader_controls": [{"kind": "allowed", "output": "control"}],
            "review": {"status": status},
        },
    )


@pytest.mark.parametrize("result", ["invalid", 42, Judgment("invalid"), Judgment(["accept"])])
def test_invalid_grader_values_become_failures_with_audit_metadata(result):
    judgment = asyncio.run(call_grader(lambda *args: result, {"allowed": [], "forbidden": []}, "x"))
    assert judgment.verdict is None
    assert judgment.failure["stage"] == "judge"
    assert judgment.failure["error_code"].startswith("invalid_grader_")
    assert len(judgment.metadata["candidate_sha256"]) == 64
    assert len(judgment.metadata["rubric_sha256"]) == 64
    assert "latency_ms" in judgment.metadata


def test_invalid_judgment_retains_attempts_output_and_provider_metadata():
    original = Judgment(
        "invalid",
        attempts=({"input_tokens": 3},),
        output={"response": "retained"},
        metadata={"model": "fixture"},
    )
    result = asyncio.run(call_grader(lambda *args: original, {"allowed": [], "forbidden": []}, "x"))
    assert result.failure is not None
    assert result.attempts == original.attempts and result.output == original.output
    assert result.metadata["model"] == "fixture"


@pytest.mark.parametrize("status", ["approved", "pending", "unreviewed"])
def test_candidate_and_controls_record_the_same_invalid_verdict_failure(status):
    async def execute(*args):
        return Execution({"question": "saved candidate"})

    result = asyncio.run(
        run_cases(
            [fixture(status)],
            execute,
            metadata={},
            grader=lambda *args: "invalid",
            diagnostic_judge=True,
        )
    )
    row = result["cases"][0]
    field = "judge" if status == "approved" else "diagnostic_judge"
    assert row[field]["failure"]["stage"] == "judge"
    assert row["status"] == "succeeded" and row["output"] == {"question": "saved candidate"}
    if status == "approved":
        assert row["quality"] == "judge_error"
        assert result["grader_controls"]["controls"][0]["judge"]["failure"]["stage"] == "judge"
    else:
        assert row["quality"] == "excluded_" + status
        assert result["summary"]["automatic_checks"]["diagnostic_judge_execution"]["failed"] == 1
    assert result["summary"]["quality_passes"] == 0


def test_rejudge_normalizes_invalid_result_and_preserves_previous_output():
    async def execute(*args):
        return Execution({"question": "saved candidate"})

    cases = [fixture()]
    previous = asyncio.run(run_cases(cases, execute, metadata={}))
    original = copy.deepcopy(previous)
    result = asyncio.run(rejudge_cases(cases, previous, lambda *args: "invalid", metadata={}))
    assert result["cases"][0]["judge"]["failure"]["stage"] == "judge"
    assert result["cases"][0]["output"] == previous["cases"][0]["output"]
    assert result["summary"]["verdicts"] == {"error": 1}
    assert previous == original


@pytest.mark.parametrize("verdict", ["accept", "reject", "ambiguous"])
def test_valid_verdicts_are_successful_judge_executions(verdict):
    judgment = asyncio.run(
        call_grader(lambda *args: verdict, {"allowed": [], "forbidden": []}, "x")
    )
    assert judgment.verdict == verdict and judgment.failure is None


def test_budget_not_executed_failure_is_preserved_without_fabricating_a_verdict():
    original = Judgment(
        None, failure={"stage": "budget", "error_code": "evaluation_budget_exhausted"}
    )
    result = asyncio.run(call_grader(lambda *args: original, {"allowed": [], "forbidden": []}, "x"))
    assert result.verdict is None and result.failure == original.failure
