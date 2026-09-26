"""The BE storage boundary accepts validated candidates, never raw model output."""

import json

import pytest
from devon_ai import contracts as c

from app.agents import contracts as adapter


def metadata():
    return c.AttemptMetadata(1, "openai", "fixture-model", "fixture-v1", "1", 1, None, None)


def question():
    contract = c.QuestionContract(
        "선정 이유",
        (c.RequiredPoint("choice", "선정 이유 설명"),),
        (),
        (),
        "선정 이유만 확인",
    )
    candidate = c.Question("tech_lead", "선정 이유는 무엇인가요?", "choice", contract, (), ())
    return c.validate_question(
        candidate,
        review=c.QuestionReview(candidate.text, contract),
        allowed_personas=("tech_lead",),
        evidence_refs=frozenset(),
        basis_refs=frozenset(),
        jd_requirement_ids=frozenset(),
    )


def test_question_contract_uses_existing_five_field_jsonb():
    result = c.ModelResult(question(), None, (metadata(),))
    value = adapter.to_turn_jsonb(result, column="question_contract")
    assert set(value) == {
        "purpose",
        "required_points",
        "assumptions",
        "basis_refs",
        "evaluation_scope",
    }
    assert value["required_points"] == [{"key": "choice", "description": "선정 이유 설명"}]
    assert "schema_version" not in value
    assert json.loads(json.dumps(value)) == value


def test_director_decision_is_flat_and_keeps_all_six_fields():
    candidate = c.DirectorDecision("finish", "정상 종료", None, None, (), "서버 종료 조건 충족")
    checked = c.validate_decision(
        candidate,
        question=None,
        allowed_personas=(),
        finish_allowed=True,
        allowed_locations=frozenset(),
    )
    value = adapter.to_turn_jsonb(c.ModelResult(checked, None, (metadata(),)), column="decision")
    assert set(value) == {
        "next_step",
        "intent",
        "persona",
        "target",
        "tool_requests",
        "reason_summary",
    }
    assert value["next_step"] == "finish" and value["tool_requests"] == []


def test_failed_model_result_cannot_be_saved_as_success():
    result = c.ModelResult(None, c.CallFailure("schema", "llm_failed", "Rejected"), (metadata(),))
    with pytest.raises(c.ContractError):
        adapter.to_turn_jsonb(result, column="analysis")


def test_analysis_keeps_existing_fields_and_nested_contribution_evidence():
    answer = "부하를 줄이려고 선택했습니다"
    candidate = c.AnswerAnalysis(
        "evaluated",
        "sufficient",
        (c.CoveredPoint("choice", ("부하를 줄이려고",)),),
        (),
        c.TechnicalAssessment("선정 이유 설명", ("부하를 줄이려고",), (), ()),
        c.ContributionScope("unknown", ()),
        (),
        False,
        (),
        ("기여 미확인",),
    )
    checked = c.validate_analysis(
        candidate,
        question=question(),
        answer_text=answer,
        evidence_refs=frozenset(),
        allowed_locations=frozenset(),
    )
    result = c.ModelResult(checked, None, (metadata(),))
    value = adapter.to_turn_jsonb(result, column="analysis")
    assert set(value) == {
        "evaluation_status",
        "sufficiency",
        "covered_points",
        "missing_points",
        "technical_assessment",
        "contribution_scope",
        "claim_checks",
        "needs_verification",
        "verification_requests",
        "limitations",
    }
    assert value["contribution_scope"] == {"scope": "unknown", "answer_quotes": []}
    assert json.loads(json.dumps(value)) == value


def test_raw_candidate_and_wrong_column_are_rejected():
    raw = c.ModelResult(question().data, None, (metadata(),))
    with pytest.raises(c.ContractError):
        adapter.to_turn_jsonb(raw, column="question_contract")
    checked = c.ModelResult(question(), None, (metadata(),))
    with pytest.raises(c.ContractError):
        adapter.to_turn_jsonb(checked, column="decision")
