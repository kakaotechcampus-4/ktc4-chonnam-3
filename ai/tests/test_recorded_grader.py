"""저장된 원문 판정이 정확한 후보·기준·문맥에만 결합되는지 검증한다."""

import asyncio
import copy

import pytest
from async_grader import call_grader
from eval_cases import Case
from eval_runner import Execution, ExecutionError, rejudge_cases, review_packets, run_cases
from recorded_grader import RecordedGrader


def fixture(case_id="repo-review"):
    return Case(
        case_id,
        1,
        "evidence",
        "dev",
        "project",
        {"evidence": [{"id": "readme", "path": "README.md", "text": "Redis is optional."}]},
        {
            "allowed": [{"id": "condition", "purpose": "Preserve the optional condition."}],
            "forbidden": [{"id": "required", "reason": "Do not call Redis required."}],
            "grader_controls": [{"kind": "forbidden", "output": "hidden control"}],
            "review": {"status": "unreviewed", "reviewer": None},
        },
    )


def previous(cases):
    async def execute(kind, payload):
        if payload.get("failed"):
            raise ExecutionError("input", "source_unavailable")
        return Execution({"description": "Redis is optional."})

    return asyncio.run(run_cases(cases, execute, metadata={}))


def document(packet):
    return {
        "format_version": 1,
        "reviewer": {
            "kind": "codex_source_review",
            "actor": "codex",
            "review_context": "implementation_session",
            "model_id": None,
        },
        "judgments": [
            {
                "binding": copy.deepcopy(packet["binding"]),
                "verdict": "accept",
                "reason_summary": "README.md states the optional condition.",
                "criterion_results": [
                    {
                        "id": "allowed:condition",
                        "status": "satisfied",
                        "reason": "Condition retained.",
                    },
                    {
                        "id": "forbidden:required",
                        "status": "satisfied",
                        "reason": "No required claim.",
                    },
                ],
            }
        ],
    }


def test_export_uses_original_candidate_and_context_without_hidden_control_or_review():
    cases = [fixture(), fixture("unavailable")]
    cases[1].payload["failed"] = True
    saved = previous(cases)
    original = copy.deepcopy(saved)
    packets = review_packets(cases, saved)
    assert len(packets) == 1
    packet = packets[0]
    assert packet["candidate_output"] == '{"description": "Redis is optional."}'
    assert packet["source_context"]["source_materials_provided"] is True
    assert set(packet["rubric"]) == {"allowed", "forbidden"}
    assert "review" not in packet and "grader_controls" not in packet
    assert len(packet["binding"]["source_context_sha256"]) == 64
    assert saved == original


def test_recorded_judge_reuses_source_bound_review_without_approving_case():
    case = fixture()
    saved = previous([case])
    packet = review_packets([case], saved)[0]
    grader = RecordedGrader(document(packet))
    result = asyncio.run(rejudge_cases([case], saved, grader, metadata={}))
    row = result["cases"][0]
    assert row["judge"]["verdict"] == "accept"
    assert row["judge"]["metadata"]["reviewer"]["kind"] == "codex_source_review"
    assert row["review_status"] == "unreviewed"
    assert result["summary"]["service_model_calls"] == 0
    assert result["summary"]["release_gate_passed"] is None
    assert row["output"] == saved["cases"][0]["output"]


@pytest.mark.parametrize("field", ["rubric", "candidate_output", "source_context"])
def test_review_does_not_match_changed_criterion_output_or_source(field):
    case = fixture()
    packet = review_packets([case], previous([case]))[0]
    grader = RecordedGrader(document(packet))
    changed = copy.deepcopy(packet)
    if field == "rubric":
        changed[field]["allowed"][0]["purpose"] = "Different requirement."
    elif field == "candidate_output":
        changed[field] = '{"description": "Redis is required."}'
    else:
        changed[field]["source"]["evidence"][0]["text"] = "Different source."
    result = asyncio.run(
        call_grader(
            grader,
            changed["rubric"],
            changed["candidate_output"],
            source_context=changed["source_context"],
        )
    )
    assert result.verdict is None
    assert result.failure["error_code"] == "recorded_judgment_not_found"


@pytest.mark.parametrize("change", ["duplicate", "contradiction", "unknown_field", "fake_human"])
def test_invalid_record_files_are_rejected(change):
    case = fixture()
    data = document(review_packets([case], previous([case]))[0])
    if change == "duplicate":
        data["judgments"].append(copy.deepcopy(data["judgments"][0]))
    elif change == "contradiction":
        data["judgments"][0]["criterion_results"][0]["status"] = "violated"
    elif change == "unknown_field":
        data["judgments"][0]["human_approved"] = True
    else:
        data["reviewer"]["kind"] = "human_approved"
    with pytest.raises(ValueError):
        RecordedGrader(data)


def test_every_current_criterion_must_have_one_recorded_result():
    case = fixture()
    packet = review_packets([case], previous([case]))[0]
    data = document(packet)
    data["judgments"][0]["criterion_results"].pop()
    result = asyncio.run(
        call_grader(
            RecordedGrader(data),
            packet["rubric"],
            packet["candidate_output"],
            source_context=packet["source_context"],
        )
    )
    assert result.verdict is None and result.failure is not None


def test_export_rejects_changed_previous_output_and_original_failure_is_preserved():
    cases = [fixture(), fixture("failed")]
    cases[1].payload["failed"] = True
    saved = previous(cases)
    packet = review_packets(cases, saved)[0]
    result = asyncio.run(rejudge_cases(cases, saved, RecordedGrader(document(packet)), metadata={}))
    assert result["cases"][1]["original_service_status"] == "failed"
    assert result["cases"][1]["original_error_code"] == "source_unavailable"
    saved["cases"][0]["output"] = {"description": "tampered"}
    with pytest.raises(ValueError, match="output hash"):
        review_packets(cases, saved)


def test_invalid_reviewer_context_is_a_validation_error():
    case = fixture()
    data = document(review_packets([case], previous([case]))[0])
    data["reviewer"]["review_context"] = []
    with pytest.raises(ValueError):
        RecordedGrader(data)


@pytest.mark.parametrize("status,verdict", [("violated", "reject"), ("unclear", "ambiguous")])
def test_recorded_negative_and_undecidable_findings_remain_distinct(status, verdict):
    case = fixture()
    packet = review_packets([case], previous([case]))[0]
    data = document(packet)
    data["judgments"][0]["criterion_results"][0]["status"] = status
    data["judgments"][0]["verdict"] = verdict
    result = asyncio.run(
        call_grader(
            RecordedGrader(data),
            packet["rubric"],
            packet["candidate_output"],
            source_context=packet["source_context"],
        )
    )
    assert result.verdict == verdict


def test_recorded_file_rejects_duplicate_json_keys_and_excess_bytes(tmp_path):
    path = tmp_path / "review.json"
    path.write_text('{"format_version":1,"format_version":2}', encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        RecordedGrader.from_path(path)
    path.write_bytes(b" " * (2 * 1024 * 1024 + 1))
    with pytest.raises(ValueError, match="byte limit"):
        RecordedGrader.from_path(path)
