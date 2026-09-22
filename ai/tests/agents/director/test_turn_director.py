import json
from dataclasses import replace

import pytest

from devon_ai import contracts as c
from devon_ai.agents.director import turn_policy as policy

HR, TECH, DOMAIN = "hr_manager", "tech_lead", "domain_lead"


def test_next_plan_and_model_context_use_confirmed_counts(
    plan, question, progress_for, run_director
):
    progress = progress_for((HR, HR, DOMAIN, HR))
    next_plan = policy.plan_question(progress, "q-5", plan.contract, remaining_candidates=2)
    assert next_plan.turn == 5 and next_plan.allowed_personas == (TECH,)
    result, calls, _ = run_director(question, plan=next_plan, progress=progress)
    assert isinstance(result, c.QuestionReady) and result.turn == 5
    context = json.loads(calls[0].input_json)
    assert len(context["history"]) == 4
    assert context["turn_policy"] == {
        "question_count": 4,
        "completed_count": 4,
        "persona_counts": {TECH: 0, HR: 3, DOMAIN: 1},
        "tech_target": 6,
    }
    assert (progress.question_count, progress.completed_count) == (4, 4)


@pytest.mark.parametrize("changed", [{"turn": 4}, {"allowed_personas": (HR,)}])
def test_forged_plan_is_rejected_before_model(plan, progress_for, run_director, changed):
    progress = progress_for((HR,) * 4)
    next_plan = policy.plan_question(progress, "q-5", plan.contract, remaining_candidates=2)
    with pytest.raises(c.ContractError):
        run_director(plan=replace(next_plan, **changed), progress=progress)


def test_pending_or_finished_progress_has_no_next_plan(plan, progress_for, turn_record):
    ready, _ = turn_record(1)
    states = (
        policy.record_question(policy.TurnProgress(), ready),
        progress_for((HR,) * 3 + (TECH,) * 6),
    )
    for progress in states:
        with pytest.raises(c.ContractError):
            policy.plan_question(progress, "next", plan.contract, remaining_candidates=2)


def test_conflicting_history_is_rejected_before_model(plan, progress_for, run_director):
    progress = progress_for((HR, TECH))
    with pytest.raises(c.ContractError):
        run_director(plan=plan, progress=progress, history=(progress.history[1],))


def test_retry_and_rewrite_do_not_present_a_question_or_complete_an_answer(
    plan, question, progress_for, run_director
):
    progress = progress_for((HR, TECH))
    result, calls, _ = run_director("{", question, progress=progress)
    assert isinstance(result, c.QuestionReady) and len(calls) == 2
    rejected, calls, _ = run_director(
        question,
        progress=progress,
        review=lambda p, q: c.QuestionCandidateReview(p, q, True, True, False, True, True),
    )
    assert rejected.recovery.recovery == "rewrite" and len(calls) == 1
    assert (progress.question_count, progress.completed_count) == (2, 2)
    assert policy.plan_question(progress, "q-3", plan.contract, remaining_candidates=1).turn == 3


def test_finish_decision_requires_ninth_processed_answer(progress_for, turn_record):
    decision = c.DirectorDecision("finish", "면접 완료", None, None, (), "9번째 답변 처리 완료")
    eight = progress_for((HR, DOMAIN, HR) + (TECH,) * 5)
    ready, record = turn_record(9, TECH)
    pending = policy.record_question(eight, ready)
    for state in (eight, pending):
        with pytest.raises(c.ContractError):
            policy.validate_turn_decision(state, decision)
    complete = policy.complete_answer(pending, record)
    assert policy.validate_turn_decision(complete, decision).data is decision
    with pytest.raises(c.ContractError):
        policy.validate_turn_decision(
            complete,
            replace(decision, next_step="ask", persona=TECH, target="역할"),
            question=ready.result.data,
        )
