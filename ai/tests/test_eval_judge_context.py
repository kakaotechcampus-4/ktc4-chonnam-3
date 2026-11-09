"""Judge가 원문을 확인하면서 정답·검수 정보는 받지 않는 경계를 검증한다."""

import asyncio
import copy
import json
from pathlib import Path

import pytest
from async_grader import Judgment, call_grader
from eval_cases import Case, load_cases
from eval_runner import Execution, rejudge_cases, run_cases, validate_rejudge_source
from grader_check import check_grader_async
from judge_context import build_judge_context, validate_judge_context


def test_original_source_and_location_reach_context_without_filling_missing_sha():
    folder = Path(__file__).parents[1] / "evals"
    original = next(
        case
        for case in load_cases(folder, allow_legacy_report_contracts=True)
        if case.case_id == "q-0004"
    )
    payload = original.model_input()
    payload["review"] = {"text": "secret-review-label"}
    payload["evidence"][0]["grader_controls"] = [{"text": "secret-control-label"}]
    before = copy.deepcopy(payload)
    context = build_judge_context(payload)
    evidence = context["source"]["evidence"][0]
    assert evidence["text"] == original.payload["evidence"][0]["text"]
    assert evidence["ref"] == "ev1" and evidence["lines"] == "26-30"
    assert "git_ref" not in evidence and "end_line" not in evidence
    assert "secret-review-label" not in json.dumps(context)
    assert "secret-control-label" not in json.dumps(context)
    assert payload == before
    assert context["schema_version"] == "judge-context.v1"
    assert "unsupported_fields_omitted" in context["limitations"]


def test_typed_source_keeps_tool_failure_and_unanswered_turn_without_promotion():
    context = build_judge_context(
        {
            "service_task": "report",
            "service_input": {
                "turns": [{"turn_no": 1, "answer": None, "question": "why?"}],
                "tool_results": [
                    {
                        "turn_id": "t1",
                        "result": {
                            "status": "tool_error",
                            "items": [],
                            "searched_scope": ["src/api.ts"],
                            "limitations": ["not_read"],
                            "error_code": "timeout",
                        },
                    }
                ],
                "review": {"text": "must-not-leak"},
            },
        }
    )
    source = context["source"]["service_input"]
    assert source["turns"][0]["answer"] is None
    assert source["tool_results"][0]["result"]["status"] == "tool_error"
    assert source["tool_results"][0]["result"]["limitations"] == ["not_read"]
    assert "must-not-leak" not in json.dumps(context)
    assert "raw_source_not_provided" in context["limitations"]


def test_oversized_source_is_marked_unavailable_without_truncating_a_quote():
    context = build_judge_context(
        {"evidence": [{"ref": "e1", "text": "large" * 1000}]}, max_bytes=512
    )
    assert context["status"] == "unavailable" and context["source"] == {}
    assert "context_byte_limit_exceeded" in context["limitations"]
    assert len(json.dumps(context).encode()) <= 512
    assert (
        build_judge_context({"service_task": "unknown", "service_input": {}})["status"]
        == "unavailable"
    )


def test_direct_context_validation_does_not_trust_an_unfiltered_source():
    context = build_judge_context({"evidence": [{"ref": "e1", "text": "raw"}]})
    context["source"]["review"] = {"text": "must-not-leak"}
    checked = validate_judge_context(context)
    assert "must-not-leak" not in json.dumps(checked)
    with pytest.raises(ValueError):
        validate_judge_context({**context, "schema_version": "unknown"})


def test_persona_identity_is_preserved_in_legacy_and_all_typed_turn_locations():
    legacy = build_judge_context({"history": [{"persona": "tech_lead", "question": "why?"}]})
    assert legacy["source"]["history"][0]["persona"] == "tech_lead"
    data = {
        "context": {
            "persona_counts": [{"persona": "hr_manager", "count": 1}],
            "history": [{"persona": "tech_lead", "question": "why?"}],
            "evaluation_targets": [{"persona": "domain_lead", "keys": ["company_job_fit"]}],
        },
        "question": {"persona": "tech_lead", "text": "why?"},
        "turns": [{"persona": "domain_lead", "answer": None}],
    }
    projected = build_judge_context({"service_task": "director", "service_input": data})["source"][
        "service_input"
    ]
    assert projected == data


def test_actual_prior_rejected_candidate_is_history_and_never_a_raw_material():
    folder = Path(__file__).parents[1] / "evals"
    original = next(
        case
        for case in load_cases(folder, allow_legacy_report_contracts=True)
        if case.case_id == "q-0010"
    )
    context = build_judge_context(original.model_input())
    assert context["source"]["rejected_candidate"] == original.payload["rejected_candidate"]
    assert "prior_candidate_is_not_raw_source" in context["limitations"]
    only_prior = build_judge_context(
        {"rejected_candidate": {"text": "unverified claim", "reason": "no raw source"}}
    )
    assert only_prior["source_materials_provided"] is False


def test_explicit_context_protocol_preserves_two_argument_graders_and_no_typeerror_retry():
    source = build_judge_context({"materials": [{"ref": "m1", "text": "raw"}]})
    calls = []

    def legacy(rubric, output):
        calls.append((rubric, output))
        assert set(rubric) == {"allowed", "forbidden"}
        raise TypeError("internal failure")

    result = asyncio.run(
        call_grader(legacy, {"allowed": [], "forbidden": []}, "candidate", source_context=source)
    )
    assert len(calls) == 1 and result.failure["error_code"] == "TypeError"
    assert result.metadata["source_context_forwarded"] is False


def test_runner_and_calibration_forward_source_but_never_expectation_metadata():
    seen = []

    class Grader:
        def __call__(self, rubric, output):
            raise AssertionError("explicit context protocol must be used")

        async def judge_with_context(self, rubric, output, context):
            seen.append((rubric, output, context))
            return Judgment("accept")

    expectation = {
        "allowed": [{"id": "a1", "purpose": "inspect raw"}],
        "forbidden": [],
        "grader_controls": [{"kind": "allowed", "output": "candidate"}],
        "review": {"status": "approved", "author": "author-secret", "reviewer": "reviewer-secret"},
    }
    case = Case(
        "fixture",
        1,
        "question",
        "dev",
        "group-secret",
        {"evidence": [{"ref": "ev1", "text": "raw"}]},
        expectation,
    )

    async def executor(kind, payload):
        return Execution({"question": "candidate"})

    asyncio.run(run_cases([case], executor, metadata={}, grader=Grader()))
    asyncio.run(check_grader_async([case], Grader()))
    assert len(seen) >= 2
    assert all(item[2]["source"]["evidence"][0]["text"] == "raw" for item in seen)
    encoded = json.dumps(seen)
    assert "author-secret" not in encoded and "reviewer-secret" not in encoded
    assert "group-secret" not in encoded and "grader_controls" not in encoded


def test_rejudge_reuses_output_preserves_failure_and_refuses_changed_input_or_output():
    expectation = {
        "allowed": [],
        "forbidden": [],
        "grader_controls": [],
        "review": {"status": "unreviewed"},
    }
    cases = [
        Case("one", 1, "question", "dev", "group", {"question": "raw"}, expectation),
        Case("two", 1, "question", "dev", "group", {"question": "raw2"}, expectation),
    ]

    async def original(kind, payload):
        if payload["question"] == "raw2":
            from eval_runner import ExecutionError

            raise ExecutionError("semantic", "candidate_replan")
        return Execution({"question": "saved candidate"})

    previous = asyncio.run(run_cases(cases, original, metadata={}))
    calls = []

    def grader(rubric, output):
        calls.append(output)
        return "ambiguous"

    result = asyncio.run(rejudge_cases(cases, previous, grader, metadata={}))
    assert calls == [json.dumps(previous["cases"][0]["output"], ensure_ascii=False)]
    assert result["summary"]["service_model_calls"] == 0
    assert result["summary"]["rejudged_outputs"] == 1
    assert result["cases"][1]["original_service_status"] == "failed"
    assert result["cases"][1]["original_error_code"] == "candidate_replan"
    assert result["summary"]["human_review_status"] == "deferred"
    assert result["summary"]["release_gate_passed"] is None
    changed = copy.deepcopy(previous)
    changed["cases"][0]["output"]["question"] = "tampered"
    with pytest.raises(ValueError, match="output hash"):
        validate_rejudge_source(cases, changed)
    changed = copy.deepcopy(previous)
    changed["cases"][0]["expectation_hash"] = "changed"
    with pytest.raises(ValueError, match="case hash"):
        validate_rejudge_source(cases, changed)
