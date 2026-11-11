"""v12는 전체 과거 발언과 분석을 보존하며 새 목적을 추측해 만들지 않는다."""

from copy import deepcopy

import pytest

from devon_ai import contracts as c
from devon_ai.agents.director.model_input import project_model_input


def analysis(sufficiency="sufficient", status="evaluated"):
    return {
        "evaluation_status": status,
        "sufficiency": sufficiency,
        "covered_points": [{"key": "flow", "answer_quotes": ["응답 경로를 설명했습니다."]}],
        "missing_points": [] if sufficiency == "sufficient" else ["scope"],
        "technical_assessment": {
            "explanation": "제공된 정적 원문에 대한 설명이다.",
            "answer_quotes": ["응답 경로를 설명했습니다."],
            "evidence_refs": ["e-4"],
            "limitations": ["실제 실행은 관찰하지 않았다."],
        },
        "contribution_scope": {"scope": "unknown", "answer_quotes": []},
        "claim_checks": [
            {
                "claim_text": "운영 결과는 확인하지 않았습니다.",
                "status": "unverified",
                "evidence_refs": [],
                "limitations": ["운영 결과의 근거가 없다."],
            }
        ],
        "needs_verification": False,
        "verification_requests": [],
        "limitations": ["개인 구현이나 기여는 확인하지 않았다."],
        "external_queries": [],
    }


def payload():
    extra = "각 예외가 어떤 조건으로 발생하는지까지 이 파일만으로 확정하지 않겠습니다."
    return {
        "context": {
            "history": [
                {
                    "turn_id": "turn-1",
                    "persona": "hr_manager",
                    "question": "직접 한 일과 팀의 일을 구분해 주세요.",
                    "answer": "팀의 작업이며 제 개인 구현으로 주장하지 않습니다.",
                    "analysis_ref": None,
                },
                {
                    "turn_id": "turn-4",
                    "persona": "tech_lead",
                    "question": "응답 경로를 설명해 주세요.",
                    "answer": "응답 경로를 설명했습니다. 운영 결과는 확인하지 않았습니다. " + extra,
                    "analysis_ref": "analysis-4",
                },
                {
                    "turn_id": "turn-8",
                    "persona": "tech_lead",
                    "question": "현재 질문의 조건을 설명해 주세요.",
                    "answer": "현재 조건은 구분했지만 이유는 모르겠습니다.",
                    "analysis_ref": "analysis-8",
                },
            ],
            "current_question_contract": {"purpose": "현재 질문의 조건과 이유"},
            "limits": {"remaining_calls": 2, "remaining_replans": 0, "policy_version": "fixed"},
            "supplemental_limitations": ["원문 일부만 제공됐다."],
        },
        "current_answer": {
            "turn_id": "turn-8",
            "question": "현재 질문의 조건을 설명해 주세요.",
            "answer": "현재 조건은 구분했지만 이유는 모르겠습니다.",
            "question_contract": {"purpose": "현재 질문의 조건과 이유"},
        },
        "answer_analysis": analysis("partial"),
        "prior_analyses": {"turn-4": analysis(), "turn-8": analysis("partial")},
        "reference_texts": [],
        "tool_results": [{"status": "not_found", "data": [], "limitations": ["미확인"]}],
        "turn_state": {"next_question_no": 9, "answered_turn_count": 8},
    }


def project(value):
    return project_model_input(value, {}, current_turn_id="turn-8", structured_dialogue=True)[0]


def test_dialogue_keeps_the_volunteered_statement_absent_from_analysis_quotes():
    original = payload()
    before = deepcopy(original)
    result = project(original)
    assert result["input_version"] == "director-input.v2"
    assert "history" not in result["context"] and "prior_analyses" not in result
    rows = result["answered_turns"]
    assert [row["turn_id"] for row in rows] == ["turn-1", "turn-4"]
    expected = original["context"]["history"][1]
    assert {key: rows[1][key] for key in expected} == expected
    assert rows[1]["goal_source"] == "question"
    assert rows[1]["analysis"] == original["prior_analyses"]["turn-4"]
    assert "각 예외가 어떤 조건으로 발생하는지" in rows[1]["answer"]
    assert result["current_answer"] == original["current_answer"]
    assert result["answer_analysis"] == original["answer_analysis"]
    assert result["turn_state"] == original["turn_state"]
    assert result["context"]["limits"] == original["context"]["limits"]
    assert result["tool_results"] == original["tool_results"]
    assert original == before
    rows[1]["analysis"]["limitations"].append("표시용 변경")
    assert original == before


def test_missing_prior_analysis_is_unavailable_without_claiming_sufficiency():
    original = payload()
    original["prior_analyses"] = {}
    rows = project(original)["answered_turns"]
    assert all(row["analysis"] is None and row["analysis_status"] == "unavailable" for row in rows)
    assert all("purpose" not in row and "completed" not in row for row in rows)


@pytest.mark.parametrize(
    ("status", "sufficiency"),
    [("evaluated", "partial"), ("needs_clarification", None), ("not_evaluable", None)],
)
def test_dialogue_preserves_partial_unknown_claim_and_contribution_limits(status, sufficiency):
    original = payload()
    old = analysis(sufficiency, status)
    original["prior_analyses"]["turn-4"] = old
    row = project(original)["answered_turns"][1]
    assert row["analysis_status"] == "provided"
    assert row["analysis"] == old
    assert row["analysis"]["sufficiency"] == sufficiency
    assert row["analysis"]["claim_checks"][0]["status"] == "unverified"
    assert row["analysis"]["contribution_scope"]["scope"] == "unknown"


def test_equal_point_keys_in_different_turns_remain_separate_observations():
    original = payload()
    other = deepcopy(original["context"]["history"][1])
    other.update(
        turn_id="turn-5", question="다른 실패 조건을 설명해 주세요.", answer="다른 조건입니다."
    )
    original["context"]["history"].insert(2, other)
    second = deepcopy(original["prior_analyses"]["turn-4"])
    second["covered_points"][0]["answer_quotes"] = ["다른 조건입니다."]
    original["prior_analyses"]["turn-5"] = second
    rows = project(original)["answered_turns"]
    assert [row["turn_id"] for row in rows] == ["turn-1", "turn-4", "turn-5"]
    assert rows[1]["analysis"]["covered_points"][0]["key"] == "flow"
    assert rows[2]["analysis"]["covered_points"][0]["key"] == "flow"
    assert rows[1]["answer"] != rows[2]["answer"]


def test_normal_dont_know_answer_remains_observable_without_automatic_failure():
    original = payload()
    original["context"]["history"][1]["answer"] = "모르겠습니다. 실행해 본 적도 없습니다."
    old = analysis("insufficient")
    old["covered_points"] = []
    old["technical_assessment"].update(
        explanation="모름 응답이며 잘못된 구현 주장으로 바꾸지 않는다.",
        answer_quotes=[],
        evidence_refs=[],
    )
    old["claim_checks"] = []
    original["prior_analyses"]["turn-4"] = old
    row = project(original)["answered_turns"][1]
    assert row["answer"] == "모르겠습니다. 실행해 본 적도 없습니다."
    assert row["analysis"]["evaluation_status"] == "evaluated"
    assert row["analysis"]["sufficiency"] == "insufficient"
    assert row["analysis"] == old
    assert "failed" not in row and "completed" not in row


def test_dialogue_keeps_the_same_projected_sources_and_hidden_posting_excluded():
    source = c.BasisRef("job_posting", "posting-1")
    text = '{"company_name":"sample","raw_text":"원문","fetch_debug":"private"}'
    old, old_sources = project_model_input(payload(), {source: text}, current_turn_id="turn-8")
    new, new_sources = project_model_input(
        payload(), {source: text}, current_turn_id="turn-8", structured_dialogue=True
    )
    assert new_sources == old_sources
    assert new["reference_texts"] == old["reference_texts"]
    assert "fetch_debug" not in new_sources[source]
