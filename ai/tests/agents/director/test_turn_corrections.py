import json
from dataclasses import asdict, replace

import pytest

from devon_ai import contracts as c
from devon_ai.agents.director import turn_policy as policy

HR, TECH, DOMAIN = "hr_manager", "tech_lead", "domain_lead"


def checked(question):
    return c.validate_question(
        question,
        review=c.QuestionReview(question.text, question.question_contract),
        allowed_personas=(question.persona,),
        evidence_refs=frozenset(),
        basis_refs=frozenset(),
        jd_requirement_ids=frozenset(),
    )


def analyzed(question, answer, analysis):
    return c.AnalysisHistory(
        question,
        answer,
        c.validate_analysis(
            analysis,
            question=question,
            answer_text=answer.text,
            evidence_refs=frozenset(),
            allowed_locations=frozenset(),
        ),
    )


@pytest.fixture
def corrected_progress(turn_record):
    def make(wrong_premise=False):
        ready, original = turn_record(1)
        original = analyzed(
            original.question,
            replace(original.answer, text="제가 구현했습니다"),
            replace(
                original.analysis.data,
                covered_points=(c.CoveredPoint("role", ("제가 구현했습니다",)),),
                contribution_scope="self",
                contribution_quotes=("제가 구현했습니다",),
            ),
        )
        progress = policy.complete_answer(
            policy.record_question(policy.TurnProgress(), ready), original
        )
        ready, correction = turn_record(2, TECH)
        if wrong_premise:
            contract = c.QuestionContract(
                "직접 구현한 캐시 방식 확인",
                (c.RequiredPoint("implementation", "구현 방식"),),
                ("사용자가 직접 구현함",),
                (),
                "캐시 구현 방식",
            )
            question = checked(
                replace(
                    correction.question.data,
                    text="직접 구현한 캐시 방식을 설명해 주세요",
                    question_contract=contract,
                )
            )
            correction = analyzed(
                question,
                correction.answer,
                replace(
                    correction.analysis.data,
                    evaluation_status="not_evaluable",
                    sufficiency=None,
                    covered_points=(),
                    missing_points=(),
                    limitations=("직접 구현 전제가 정정되어 평가 보류",),
                ),
            )
            ready = replace(ready, result=c.ModelSuccess(question, ()))
        progress = policy.complete_answer(policy.record_question(progress, ready), correction)
        return progress

    return make


@pytest.mark.parametrize("wrong_premise", [False, True])
def test_correction_keeps_question_specific_analysis_in_final_feedback(
    corrected_progress, turn_record, wrong_premise
):
    progress = corrected_progress(wrong_premise)
    before = asdict(progress)
    correction = progress.history[1].analysis.data
    assert correction.contribution_scope == "teammate"
    if wrong_premise:
        assert correction.evaluation_status == "not_evaluable" and correction.sufficiency is None
    else:
        assert correction.sufficiency == "sufficient"
        assert correction.covered_points[0].key == "role"
    for turn, persona in enumerate((HR, DOMAIN) + (TECH,) * 5, 3):
        ready, record = turn_record(turn, persona)
        progress = policy.complete_answer(policy.record_question(progress, ready), record)
    context = policy.feedback_context(progress)
    first, second = context["turns"][:2]
    assert first["question_id"] == "q-1" and second["question_id"] == "q-2"
    assert first["analysis"]["contribution_scope"] == "self"
    assert second["analysis"]["contribution_scope"] == "teammate"
    assert second["analysis"]["sufficiency"] == (None if wrong_premise else "sufficient")
    assert first["answer"]["text"] == "제가 구현했습니다"
    assert second["answer"]["text"] == "팀원이 구현했습니다"
    assert [row["answer"]["turn"] for row in context["turns"]] == list(range(1, 10))
    assert asdict(progress.history[0]) == before["history"][0]
    # Modifying a consumer payload must not edit the original persisted projection.
    second["analysis"]["contribution_scope"] = "self"
    assert progress.history[1].analysis.data.contribution_scope == "teammate"


def test_correction_replans_stale_premise_without_reassessing_prior_answer(
    corrected_progress, run_director
):
    progress = corrected_progress(True)
    before = asdict(progress)
    stale = progress.history[1].question.data
    plan = policy.plan_question(progress, "q-3", stale.question_contract, remaining_candidates=2)

    def independent_review(current_plan, candidate):
        return c.QuestionCandidateReview(current_plan, candidate, False, True, True, True, True)

    result, calls, _ = run_director(stale, plan=plan, progress=progress, review=independent_review)
    assert isinstance(result, c.QuestionRejected) and result.recovery.recovery == "replan"
    history = json.loads(calls[0].input_json)["history"]
    assert history[1]["analysis"]["contribution_scope"] == "teammate"
    assert history[1]["question"]["question_contract"]["assumptions"] == ["사용자가 직접 구현함"]
    assert asdict(progress) == before


def test_feedback_requires_all_nine_answers_processed(corrected_progress, turn_record):
    progress = corrected_progress()
    with pytest.raises(c.ContractError):
        policy.feedback_context(progress)
    for turn, persona in enumerate((HR, DOMAIN) + (TECH,) * 4, 3):
        ready, record = turn_record(turn, persona)
        progress = policy.complete_answer(policy.record_question(progress, ready), record)
    pending = policy.record_question(progress, turn_record(9, TECH)[0])
    with pytest.raises(c.ContractError):
        policy.feedback_context(pending)


@pytest.mark.skip(reason="AI-L09: 과거 입력 편집·복구·재평가 계약 미채택; 완료로 간주하지 않음")
def test_historical_input_edit_and_reassessment_policy_pending():
    """새로운 발언 반영과 달리 과거 입력 복구/재평가 API는 이번 범위에 없다."""
