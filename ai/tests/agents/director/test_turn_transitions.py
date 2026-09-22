from dataclasses import replace

import pytest

from devon_ai import contracts as c
from devon_ai.agents.director import turn_policy as policy

HR, TECH, DOMAIN = "hr_manager", "tech_lead", "domain_lead"


def test_question_and_processed_answer_are_separate_immutable_transitions(turn_record):
    empty = policy.TurnProgress()
    ready, record = turn_record(1)
    pending = policy.record_question(empty, ready)
    assert (empty.question_count, empty.completed_count) == (0, 0)
    assert (pending.question_count, pending.completed_count) == (1, 0)
    assert not policy.finish_allowed(pending)
    complete = policy.complete_answer(pending, record)
    assert (complete.question_count, complete.completed_count) == (1, 1)
    assert pending.completed_count == 0
    assert complete.questions[0].question is record.question
    assert complete.history[0] is record


def test_repeated_question_or_answer_cannot_advance_turn(turn_record):
    ready, record = turn_record(1)
    pending = policy.record_question(policy.TurnProgress(), ready)
    with pytest.raises(c.ContractError):
        policy.record_question(pending, ready)
    with pytest.raises(c.ContractError):
        policy.record_question(pending, turn_record(2, TECH)[0])
    complete = policy.complete_answer(pending, record)
    with pytest.raises(c.ContractError):
        policy.complete_answer(complete, record)
    with pytest.raises(c.ContractError):
        policy.record_question(complete, replace(turn_record(2, TECH)[0], question_id="q-1"))


def test_mismatched_turn_or_changed_question_cannot_complete_answer(turn_record):
    ready, record = turn_record(1)
    pending = policy.record_question(policy.TurnProgress(), ready)
    for wrong in (replace(record, answer=replace(record.answer, turn=2)), turn_record(1, TECH)[1]):
        with pytest.raises(c.ContractError):
            policy.complete_answer(pending, wrong)
    assert pending.questions[0].question.data.persona == HR


def test_only_ninth_processed_answer_allows_finish_and_never_tenth_question(
    progress_for, turn_record
):
    eight = progress_for((HR, DOMAIN, HR) + (TECH,) * 5)
    ready, record = turn_record(9, TECH)
    assert not policy.finish_allowed(eight)
    pending = policy.record_question(eight, ready)
    assert not policy.finish_allowed(pending)
    completed = policy.complete_answer(pending, record)
    assert policy.finish_allowed(completed)
    with pytest.raises(c.ContractError):
        policy.record_question(completed, replace(ready, turn=10, question_id="q-10"))
    with pytest.raises(c.ContractError):
        policy.complete_answer(completed, record)


@pytest.mark.parametrize("turn", [0, 2, True, "1"])
def test_wrong_question_turn_is_rejected(turn_record, turn):
    ready, _ = turn_record(1)
    with pytest.raises(c.ContractError):
        policy.record_question(policy.TurnProgress(), replace(ready, turn=turn))


def test_unchecked_or_failed_result_is_not_a_presented_question(turn_record):
    ready, _ = turn_record(1)
    for wrong in (
        replace(ready, result=c.ModelSuccess(ready.result.data.data, ())),
        c.QuestionRejected(
            "q-1",
            c.ModelFailed(c.ModelFailure("semantic"), ()),
            c.CandidateRecovery("no_valid_candidate", "상한 소진"),
        ),
    ):
        with pytest.raises(c.ContractError):
            policy.record_question(policy.TurnProgress(), wrong)


def test_restore_requires_contiguous_exact_history(progress_for, turn_record):
    progress = progress_for((HR, TECH))
    for changes in (
        {"history": ()},
        {"history": tuple(reversed(progress.history))},
        {"questions": list(progress.questions)},
        {"history": (progress.history[1],)},
    ):
        with pytest.raises(c.ContractError):
            replace(progress, **changes)
    with pytest.raises(c.ContractError):
        replace(progress.questions[0], question_id="")
