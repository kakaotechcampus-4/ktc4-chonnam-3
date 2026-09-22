import json
from dataclasses import replace

import pytest

from devon_ai import contracts as c


def test_plan_pins_question_identity_requirements_and_controller_permissions(plan):
    assert plan.question_id == "question-3" and plan.turn == 3
    assert plan.contract.required_points[0].key == "writes"
    assert plan.allowed_personas == ("tech_lead", "domain_lead")


@pytest.mark.parametrize(
    "change",
    [
        {"question_id": " "},
        {"turn": 0},
        {"turn": 10},
        {"turn": True},
        {"allowed_personas": ("MANAGER",)},
        {"allowed_personas": ("tech_lead", "tech_lead")},
        {"remaining_candidates": -1},
        {"remaining_candidates": True},
        {"remaining_candidates": 1.5},
    ],
)
def test_invalid_plan_is_rejected_before_generation(plan, change):
    with pytest.raises(c.ContractError):
        replace(plan, **change)


def test_exhausted_or_empty_permissions_can_be_represented_without_defaults(plan):
    assert replace(plan, remaining_candidates=0).remaining_candidates == 0
    assert replace(plan, allowed_personas=()).allowed_personas == ()


def test_generation_uses_prepared_contract_and_returns_only_checked_question(
    plan,
    question,
    run_director,
):
    result, calls, reviews = run_director(question)
    assert isinstance(result, c.QuestionReady)
    assert result.question_id == plan.question_id and result.turn == 3
    assert isinstance(result.result.data, c.ContractChecked)
    assert result.result.data.data == question
    payload = json.loads(calls[0].input_json)
    assert payload["plan"]["contract"]["required_points"] == [
        {"key": "writes", "description": "수정 특성"}
    ]
    assert {p["persona"] for p in payload["personas"]} == {"tech_lead", "hr_manager", "domain_lead"}
    assert len(calls) == len(reviews) == 1


@pytest.mark.parametrize("change", [{"allowed_personas": ()}, {"remaining_candidates": 0}])
def test_controller_denial_stops_before_model_call(plan, run_director, change):
    result, calls, reviews = run_director(plan=replace(plan, **change))
    assert isinstance(result, c.QuestionRejected)
    assert result.recovery.recovery == "no_valid_candidate"
    assert calls == reviews == [] and result.failure.attempts == ()


def test_unknown_prepared_basis_is_rejected_before_call(plan, run_director):
    invalid = replace(plan, contract=replace(plan.contract, basis_refs=("unknown",)))
    with pytest.raises(c.ContractError):
        run_director(plan=invalid)


def test_wrong_persona_never_reaches_semantic_reviewer(question, run_director):
    result, calls, reviews = run_director(replace(question, persona="hr_manager"))
    assert isinstance(result, c.QuestionRejected) and result.failure.failure.stage == "semantic"
    assert len(calls) == 1 and reviews == []
    assert not hasattr(result, "question") and not hasattr(result, "data")


@pytest.mark.parametrize("binding", ["question_id", "text"])
def test_review_must_belong_to_exact_question_and_id(plan, question, run_director, binding):
    def stale(current, candidate):
        if binding == "question_id":
            current = replace(current, question_id="other-question")
        else:
            candidate = replace(candidate, text="예전 질문")
        return c.QuestionCandidateReview(current, candidate, True, True, True, True, True)

    result, calls, _ = run_director(question, review=stale)
    assert isinstance(result, c.QuestionRejected)
    assert result.failure.failure.stage == "semantic" and len(calls) == 1
