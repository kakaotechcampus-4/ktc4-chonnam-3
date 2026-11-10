"""실행 입력과 평가 정답의 분리 및 검수 분모를 검증한다."""

import asyncio
from dataclasses import replace

from eval_cases import Case
from eval_runner import Execution, ExecutionError, run_cases


def test_automatic_validation_of_unreviewed_output_is_separate_from_human_approval():
    async def execute(kind, payload):
        return Execution({"question": "generated"})

    result = asyncio.run(run_cases([case()], execute, metadata={"mode": "execute"}))
    checks = result["summary"]["automatic_checks"]
    assert checks["input_contract"]["status"] == "passed"
    assert checks["service_execution"] == {
        "status": "passed",
        "total": 1,
        "passed": 1,
        "failed": 0,
        "not_executed": 0,
    }
    assert result["summary"]["human_review_status"] == "deferred"
    assert result["summary"]["quality_passes"] == 0
    assert result["summary"]["release_gate_passed"] is None


def test_dry_run_only_completes_the_input_contract_check():
    async def execute(kind, payload):
        return Execution({"input_valid": True}, validated_only=True)

    result = asyncio.run(run_cases([case()], execute, metadata={"mode": "validate"}))
    checks = result["summary"]["automatic_checks"]
    assert checks["input_contract"]["status"] == "passed"
    assert checks["service_execution"]["status"] == "not_executed"
    assert checks["service_execution"]["not_executed"] == 1


def test_bad_binding_cannot_be_counted_as_an_automatic_service_success():
    async def execute(kind, payload):
        raise ExecutionError("input", "explicit_service_input_required")

    result = asyncio.run(run_cases([case()], execute, metadata={"mode": "execute"}))
    checks = result["summary"]["automatic_checks"]
    assert checks["input_contract"]["status"] == "failed"
    assert checks["service_execution"]["status"] == "not_executed"
    assert checks["service_execution"]["passed"] == 0


def test_explicit_diagnostic_judge_does_not_approve_an_unreviewed_case():
    async def execute(kind, payload):
        return Execution({"question": "generated"})

    result = asyncio.run(
        run_cases(
            [case()],
            execute,
            metadata={},
            grader=lambda rubric, output: "reject",
            diagnostic_judge=True,
        )
    )
    assert result["cases"][0]["diagnostic_judge"]["verdict"] == "reject"
    assert result["cases"][0]["quality"] == "excluded_unreviewed"
    assert result["summary"]["diagnostic_verdicts"] == {"reject": 1}
    assert result["summary"]["automatic_checks"]["diagnostic_judge_execution"]["status"] == "passed"
    assert result["summary"]["quality_denominator"] == 0
    assert result["summary"]["release_gate_passed"] is None


def test_report_form_is_checked_automatically_without_human_approval():
    async def execute(kind, payload):
        return Execution({"scores": [], "totalScore": 99})

    result = asyncio.run(run_cases([replace(case(), kind="report")], execute, metadata={}))
    checks = result["summary"]["automatic_checks"]
    assert checks["service_execution"]["status"] == "passed"
    assert checks["report_form"]["status"] == "failed"
    assert result["summary"]["quality_denominator"] == 0


def test_judge_budget_exhaustion_is_partial_instead_of_a_completed_control_check():
    from async_grader import Judgment

    fixture = case("approved")
    fixture.expectation["grader_controls"] = [
        {"kind": "allowed", "output": "good"},
        {"kind": "forbidden", "output": "bad"},
    ]

    async def execute(kind, payload):
        raise AssertionError("control calibration must not execute the service")

    async def judge(rubric, output):
        return (
            Judgment("accept")
            if output == "good"
            else Judgment(
                None, failure={"stage": "budget", "error_code": "evaluation_budget_exhausted"}
            )
        )

    result = asyncio.run(
        run_cases([fixture], execute, metadata={}, grader=judge, calibration_only=True)
    )
    assert result["summary"]["automatic_checks"]["judge_controls"] == {
        "status": "partial",
        "total": 2,
        "passed": 1,
        "failed": 0,
        "not_executed": 1,
    }


def test_unexecuted_diagnostic_due_to_budget_is_not_a_wrong_answer_or_a_provider_failure():
    from async_grader import Judgment

    async def execute(kind, payload):
        return Execution({"question": "generated"})

    calls = []

    async def judge(rubric, output):
        calls.append(output)
        return (
            Judgment("accept")
            if len(calls) == 1
            else Judgment(
                None, failure={"stage": "budget", "error_code": "evaluation_budget_exhausted"}
            )
        )

    result = asyncio.run(
        run_cases(
            [case(), case(case_id="q-9998")],
            execute,
            metadata={},
            grader=judge,
            diagnostic_judge=True,
        )
    )
    check = result["summary"]["automatic_checks"]["diagnostic_judge_execution"]
    assert check == {"status": "partial", "total": 2, "passed": 1, "failed": 0, "not_executed": 1}
    assert result["summary"]["diagnostic_verdicts"] == {"accept": 1, "not_executed": 1}


def test_invalid_diagnostic_verdict_is_failed_instead_of_not_executed():
    async def execute(kind, payload):
        return Execution({"question": "generated"})

    result = asyncio.run(
        run_cases(
            [case()],
            execute,
            metadata={},
            grader=lambda rubric, output: "invalid-verdict",
            diagnostic_judge=True,
        )
    )
    assert result["summary"]["automatic_checks"]["diagnostic_judge_execution"]["failed"] == 1
    assert result["summary"]["diagnostic_verdicts"] == {"error": 1}


def case(status="unreviewed", case_id="q-9999"):
    return Case(
        case_id,
        1,
        "question",
        "dev",
        case_id,
        {"service_input": {"visible": "source"}},
        {
            "allowed": ["rubric"],
            "forbidden": ["secret expectation"],
            "grader_controls": [],
            "review": {"status": status},
        },
    )


def test_executor_receives_only_detached_payload_not_expectation_control_or_review():
    fixture = case("approved")
    seen = []

    async def execute(kind, payload):
        seen.append((kind, payload.copy()))
        payload["service_input"]["visible"] = "mutated"
        return Execution({"question": "generated"})

    result = asyncio.run(run_cases([fixture], execute, metadata={"revision": "rev"}))
    assert seen[0][0] == "question"
    assert set(seen[0][1]) == {"service_input"}
    assert fixture.payload["service_input"]["visible"] == "source"
    assert result["summary"]["quality_passes"] == 0
    assert result["cases"][0]["quality"] == "not_graded"


def test_unreviewed_execution_records_usage_but_never_becomes_a_quality_pass():
    async def execute(kind, payload):
        return Execution(
            {"question": "generated"},
            (
                {
                    "input_tokens": 3,
                    "output_tokens": None,
                    "model": "fixture",
                    "prompt_version": "v1",
                    "schema_version": "1",
                    "latency_ms": 2,
                },
            ),
        )

    result = asyncio.run(
        run_cases([case()], execute, metadata={}, grader=lambda rubric, text: "accept")
    )
    row = result["cases"][0]
    assert row["status"] == "succeeded" and row["quality"] == "excluded_unreviewed"
    assert row["input_tokens"] == 3 and row["output_tokens"] is None
    assert row["cost_usd"] is None
    assert result["summary"]["quality_denominator"] == 0


def test_approved_outputs_need_a_judge_and_failed_execution_cannot_pass():
    async def execute(kind, payload):
        raise ExecutionError("input", "missing_question_contract")

    result = asyncio.run(
        run_cases([case("approved")], execute, metadata={}, grader=lambda rubric, text: "accept")
    )
    assert result["cases"][0]["error_code"] == "missing_question_contract"
    assert result["cases"][0]["quality"] == "execution_failed"
    assert result["summary"]["quality_passes"] == 0


def test_grader_sees_rubric_and_actual_output_without_control_kind_or_pair_metadata():
    fixture = case("approved")
    fixture.expectation["pair"] = {"secret": "hidden"}
    seen = []

    async def execute(kind, payload):
        return Execution({"question": "actual model candidate"})

    def judge(rubric, output):
        seen.append((rubric, output))
        return "ambiguous"

    result = asyncio.run(run_cases([fixture], execute, metadata={}, grader=judge))
    assert seen[0][0] == {"allowed": ["rubric"], "forbidden": ["secret expectation"]}
    assert "actual model candidate" in seen[0][1]
    assert result["summary"]["quality_passes"] == 0
    assert result["summary"]["quality_denominator"] == 1


def test_invalid_judge_does_not_discard_the_model_output_or_assert_a_release_pass():
    fixture = case("approved")
    fixture.expectation["grader_controls"] = [{"kind": "allowed", "output": "control"}]

    async def execute(kind, payload):
        return Execution({"question": "actual candidate"})

    result = asyncio.run(
        run_cases([fixture], execute, metadata={}, grader=lambda rubric, text: "invalid")
    )
    assert result["cases"][0]["output"] == {"question": "actual candidate"}
    assert result["cases"][0]["quality"] == "judge_error"
    assert result["grader_controls"]["by_kind"]["allowed"]["error"] == 1
    assert result["summary"]["automatic_checks"]["judge_controls"]["failed"] == 1
    assert result["summary"]["release_gate_passed"] is None


def test_async_judge_is_awaited_for_service_outputs_and_controls():
    fixture = case("approved")
    fixture.expectation["grader_controls"] = [{"kind": "allowed", "output": "control-only"}]
    seen = []

    async def execute(kind, payload):
        return Execution({"question": "service-only"})

    async def judge(rubric, output):
        seen.append((rubric, output))
        return "accept"

    result = asyncio.run(run_cases([fixture], execute, metadata={}, grader=judge))
    assert result["cases"][0]["quality"] == "accept"
    assert len(seen) == 2 and all(set(rubric) == {"allowed", "forbidden"} for rubric, _ in seen)
    assert result["grader_controls"]["by_kind"]["allowed"]["correct"] == 1
    assert result["summary"]["release_gate_passed"] is None


def test_calibration_only_does_not_execute_or_guess_missing_service_input():
    fixture = case("approved")
    fixture.expectation["grader_controls"] = [{"kind": "allowed", "output": "control"}]

    async def unexpected(kind, payload):
        raise AssertionError("교정 모드에서는 서비스 모델을 실행하지 않는다")

    async def judge(rubric, output):
        return "accept"

    result = asyncio.run(
        run_cases(
            [fixture],
            unexpected,
            metadata={},
            grader=judge,
            calibration_only=True,
            bindings={
                "q-9999.v1": {"status": "invalid", "error_code": "explicit_service_input_required"}
            },
        )
    )
    assert result["cases"][0]["status"] == "not_executed"
    assert result["cases"][0]["error_code"] == "explicit_service_input_required"
    assert result["summary"]["quality_denominator"] == 0
    assert result["grader_controls"]["evaluated_cases"] == 1
    assert result["summary"]["release_gate_passed"] is None
