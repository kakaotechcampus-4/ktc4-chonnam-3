from dataclasses import replace

import pytest

from devon_ai import contracts as c


def assessment(**changes):
    def review(plan, question):
        return replace(
            c.QuestionCandidateReview(plan, question, True, True, True, True, True), **changes
        )

    return review


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({"wording_valid": False}, "rewrite"),
        ({"premises_valid": False}, "replan"),
        ({"context_valid": False}, "replan"),
        ({"contract_matches": False}, "replan"),
        ({"wording_valid": False, "contract_matches": False}, "replan"),
        ({"premises_valid": False, "wording_valid": False}, "replan"),
        ({"context_valid": False, "safe_alternative": False}, "no_valid_candidate"),
    ],
)
def test_recovery_is_classified_without_automatic_semantic_retry(
    question,
    run_director,
    changes,
    expected,
):
    result, calls, _ = run_director(question, review=assessment(**changes))
    assert isinstance(result, c.QuestionRejected)
    assert result.recovery.recovery == expected
    assert result.failure.failure.stage == "semantic" and len(calls) == 1
    assert not hasattr(result, "result")


def test_missing_writes_goal_does_not_accept_a_ttl_question(question, run_director):
    normal, _, _ = run_director(question)
    assert isinstance(normal, c.QuestionReady)
    changed, calls, _ = run_director(
        replace(question, text="TTL은 몇 분인가요?"), review=assessment(contract_matches=False)
    )
    assert isinstance(changed, c.QuestionRejected)
    assert changed.recovery.recovery == "replan" and len(calls) == 1


def test_model_cannot_replace_the_prepared_contract_to_fit_its_wrong_question(
    question, run_director
):
    wrong_contract = replace(
        question.question_contract,
        purpose="TTL 확인",
        required_points=(c.RequiredPoint("ttl", "TTL 값"),),
    )
    result, _, _ = run_director(
        replace(question, text="TTL은 몇 분인가요?", question_contract=wrong_contract)
    )
    assert isinstance(result, c.QuestionRejected) and result.recovery.recovery == "replan"


@pytest.mark.parametrize("changes", [{"wording_valid": False}, {"premises_valid": False}])
def test_exhausted_budget_never_returns_the_failed_question(plan, question, run_director, changes):
    result, calls, _ = run_director(
        question, plan=replace(plan, remaining_candidates=1), review=assessment(**changes)
    )
    assert isinstance(result, c.QuestionRejected)
    assert result.recovery.recovery == "no_valid_candidate" and len(calls) == 1
    assert not hasattr(result, "question") and not hasattr(result, "next_step")


def test_valid_last_candidate_is_not_discarded(plan, question, run_director):
    result, calls, _ = run_director(question, plan=replace(plan, remaining_candidates=1))
    assert isinstance(result, c.QuestionReady) and len(calls) == 1
