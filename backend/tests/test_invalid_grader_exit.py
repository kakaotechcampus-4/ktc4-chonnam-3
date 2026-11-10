"""서비스 출력과 입력 원문을 보존하면서 Judge 오류의 CLI 종료 코드를 검증한다."""

import json

import pytest

from scripts import run_ai_evaluation as cli
from scripts.evaluation_output import technical_exit_code
from tests.test_ai_evaluation_safety import arguments


def test_passing_controls_do_not_hide_invalid_candidate_judge_in_cli(monkeypatch, tmp_path):
    from eval_cases import Case
    from eval_runner import Execution, run_cases

    case = Case(
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
            "review": {"status": "approved"},
        },
    )
    before = json.dumps(case.payload, sort_keys=True)
    output = arguments(monkeypatch, tmp_path)
    previous = tmp_path / "previous.json"
    previous.write_bytes(b"previous result must remain unchanged\n")

    async def execute(args):
        async def service(*args):
            return Execution({"question": "actual candidate"})

        return await run_cases(
            [case],
            service,
            metadata={},
            grader=lambda rubric, candidate: "accept" if candidate == "control" else "invalid",
        )

    monkeypatch.setattr(cli, "execute", execute)
    assert cli.main() == 1
    result = json.loads(output.read_text("utf-8"))
    assert result["summary"]["automatic_checks"]["judge_controls"]["status"] == "passed"
    assert result["cases"][0]["quality"] == "judge_error"
    assert result["cases"][0]["output"] == {"question": "actual candidate"}
    assert json.dumps(case.payload, sort_keys=True) == before
    assert previous.read_bytes() == b"previous result must remain unchanged\n"


def test_legacy_judge_error_quality_is_a_technical_failure_without_judge_details():
    result = {"summary": {"total": 1}, "cases": [{"quality": "judge_error", "judge": None}]}
    assert technical_exit_code(result) == 1


@pytest.mark.parametrize(
    "quality", ["reject", "ambiguous", "excluded_pending", "excluded_unreviewed"]
)
def test_valid_quality_and_deferred_human_review_do_not_fail_technical_exit(quality):
    result = {
        "summary": {"total": 1, "human_review_status": "deferred", "release_gate_passed": None},
        "cases": [{"quality": quality, "judge": None}],
    }
    assert technical_exit_code(result) == 0
