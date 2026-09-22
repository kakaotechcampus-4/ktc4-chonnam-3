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


def test_deferred_sufficiency_preserves_already_observed_points(analysis, run_analysis):
    analysis.update(
        evaluation_status="needs_clarification",
        sufficiency=None,
        missing_points=[],
        limitations=["수정 특성을 어떤 범위로 물었는지 확인 필요"],
    )
    result, _ = run_analysis(analysis)
    assert isinstance(result, c.ModelSuccess)
    assert result.data.data.sufficiency is None
    assert [point.key for point in result.data.data.covered_points] == ["reads", "choice"]


def test_technical_judgement_requires_a_quote_or_an_explicit_limit(analysis, run_analysis):
    analysis["technical_assessment"].update(answer_quotes=[], limitations=[])
    result, _ = run_analysis(analysis)
    assert isinstance(result, c.ModelFailed) and result.failure.stage == "semantic"


@pytest.mark.parametrize(
    ("status", "reason"),
    [
        ("not_evaluable", "질문이 직접 구현을 잘못 전제함"),
        ("needs_clarification", "어떤 변경을 뜻하는지 답변 해석 확인 필요"),
    ],
)
def test_question_or_interpretation_issue_is_not_missing_ability(
    analysis, run_analysis, status, reason
):
    analysis.update(
        evaluation_status=status,
        sufficiency=None,
        covered_points=[],
        missing_points=[],
        limitations=[reason],
    )
    result, _ = run_analysis(analysis)
    assert isinstance(result, c.ModelSuccess)
    assert result.data.data.evaluation_status == status
    assert result.data.data.missing_points == () and result.data.data.sufficiency is None


@pytest.mark.parametrize("mode", ["sufficient", "partial", "insufficient"])
def test_same_question_keeps_three_distinct_coverage_results(analysis, answer, run_analysis, mode):
    if mode == "sufficient":
        answer = replace(answer, text="조회가 많아서 수정은 드물고 DB 부하를 줄이려고 캐시했습니다")
        analysis["covered_points"].append({"key": "writes", "answer_quotes": ["수정은 드물고"]})
        analysis["missing_points"] = []
    elif mode == "insufficient":
        answer = replace(answer, text="모르겠습니다")
        analysis.update(covered_points=[], missing_points=["reads", "writes", "choice"])
        analysis["technical_assessment"].update(
            explanation="검증할 기술 주장이 제시되지 않음",
            answer_quotes=[],
            limitations=["기술 주장 없음; 기술 오류로 판정하지 않음"],
        )
    analysis["sufficiency"] = mode
    result, _ = run_analysis(analysis, answer=answer)
    assert isinstance(result, c.ModelSuccess)
    assert result.data.data.sufficiency == mode
    assert result.data.data.evaluation_status == "evaluated"
    assert result.data.data.claim_checks == ()


def test_long_wrong_and_short_valid_keep_accuracy_separate(analysis, answer, run_analysis):
    first, _ = run_analysis(analysis)
    assert first.data.data.sufficiency == "partial"
    assert (
        first.data.data.technical_assessment.explanation
        == "캐시 목적은 타당하나 구현 조건은 미확인"
    )
    long_answer = replace(
        answer,
        text="조회가 많아서 DB 부하를 줄이려고 캐시했습니다. "
        "수정은 실시간이며 캐시는 언제나 자동으로 최신 원본과 동기화됩니다.",
    )
    analysis.update(sufficiency="sufficient", missing_points=[])
    analysis["covered_points"].append({"key": "writes", "answer_quotes": ["수정은 실시간"]})
    analysis["technical_assessment"].update(
        explanation="항상 자동 동기화된다는 설명은 타당하지 않음; 무효화 조건 확인 필요",
        answer_quotes=["캐시는 언제나 자동으로 최신 원본과 동기화됩니다"],
    )
    second, _ = run_analysis(analysis, answer=long_answer)
    assert isinstance(second, c.ModelSuccess) and second.data.data.sufficiency == "sufficient"
    assert "타당하지 않음" in second.data.data.technical_assessment.explanation


def test_persona_does_not_change_evaluation_input_or_rubric(analysis, question, run_analysis):
    changed = replace(question.data, persona="hr_manager")
    checked = c.validate_question(
        changed,
        review=c.QuestionReview(changed.text, changed.question_contract),
        allowed_personas=("hr_manager",),
        evidence_refs=frozenset(),
        basis_refs=frozenset(),
        jd_requirement_ids=frozenset(),
    )
    first, calls1 = run_analysis(analysis)
    second, calls2 = run_analysis(analysis, question=checked)
    assert calls1[0].input_json == calls2[0].input_json
    assert calls1[0].prompt == calls2[0].prompt
    assert first.data == second.data
