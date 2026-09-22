import json
from dataclasses import replace

import pytest

from devon_ai import contracts as c


def test_confirmed_answer_retains_wire_fields_without_a_submission_identifier():
    answer = c.decode(c.SubmittedAnswer, {"type": "answer", "turn": 2, "text": "모르겠습니다"})
    assert answer.turn == 2 and answer.text == "모르겠습니다"


@pytest.mark.parametrize(
    "patch",
    [
        {"type": "draft"},
        {"turn": 0},
        {"turn": 10},
        {"turn": True},
        {"turn": "2"},
        {"text": " "},
        {"text": None},
        {"clientSubmissionId": "not-allowed"},
    ],
)
def test_invalid_submission_is_rejected(patch):
    with pytest.raises(c.ContractError):
        c.decode(c.SubmittedAnswer, dict({"type": "answer", "turn": 2, "text": "답변"}, **patch))


def test_cache_answer_is_partial_with_only_unanswered_writes(analysis, run_analysis, answer):
    result, calls = run_analysis(analysis)
    assert isinstance(result, c.ModelSuccess)
    data = result.data.data
    assert data.sufficiency == "partial" and data.missing_points == ("writes",)
    assert [point.key for point in data.covered_points] == ["reads", "choice"]
    assert data.technical_assessment.limitations == ("현재 코드 근거 없음",)
    assert data.contribution_scope == "unknown"
    payload = json.loads(calls[0].input_json)
    assert payload["answer"] == {"type": "answer", "turn": 2, "text": answer.text}
    assert payload["question"]["question_contract"]["required_points"][1]["key"] == "writes"
    assert "persona" not in payload["question"]
    assert len(calls) == 1


@pytest.mark.parametrize("invalid_turn", [1, 0, 10, True, "2"])
def test_wrong_turn_is_rejected_before_model_call(run_analysis, invalid_turn):
    with pytest.raises(c.ContractError):
        run_analysis(question_turn=invalid_turn)


def test_unchecked_question_is_rejected_before_model_call(question, run_analysis):
    with pytest.raises(c.ContractError):
        run_analysis(question=question.data)


def test_other_task_configuration_is_rejected(model_request, run_analysis):
    with pytest.raises(c.ContractError):
        run_analysis(request=replace(model_request, task_name="director_v1"))


def test_unasked_ttl_is_semantic_failure_without_retry(analysis, run_analysis):
    analysis["missing_points"].append("ttl")
    result, calls = run_analysis(analysis)
    assert isinstance(result, c.ModelFailed) and result.failure.stage == "semantic"
    assert len(calls) == 1
