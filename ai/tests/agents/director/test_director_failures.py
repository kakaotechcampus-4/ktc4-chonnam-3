import json
from dataclasses import asdict, replace

import pytest

from devon_ai import contracts as c
from devon_ai.llm_tasks import ModelProviderError


def test_review_input_error_does_not_retry_the_generator(question, run_director):
    def invalid_review(plan, candidate):
        raise c.ContractError("schema", "private review detail")

    result, calls, reviews = run_director(question, review=invalid_review)
    assert isinstance(result, c.QuestionRejected)
    assert result.failure.failure.stage == "semantic" and len(calls) == len(reviews) == 1
    assert "private review detail" not in repr(result)


@pytest.mark.parametrize(("raw", "stage"), [("broken JSON", "parse"), ("{}", "schema")])
def test_invalid_model_output_exhausts_only_common_attempts(run_director, raw, stage):
    result, calls, reviews = run_director(raw, raw)
    assert isinstance(result, c.QuestionRejected) and result.failure.failure.stage == stage
    assert len(calls) == 2 and reviews == []
    assert result.recovery.recovery == "no_valid_candidate"


@pytest.mark.parametrize("error", [TimeoutError(), ModelProviderError("private provider detail")])
def test_transport_failure_can_recover_without_changing_plan(question, run_director, error):
    result, calls, reviews = run_director(error, question)
    assert isinstance(result, c.QuestionReady)
    assert [attempt.attempt for attempt in result.result.attempts] == [1, 2]
    assert calls[0].input_json == calls[1].input_json and len(reviews) == 1


@pytest.mark.parametrize(
    "extra", [{"question_id": "made-up"}, {"review": {"passed": True}}, {"next_step": "finish"}]
)
def test_model_cannot_add_identity_self_approval_or_finish(question, run_director, extra):
    raw = json.dumps(asdict(question) | extra)
    result, calls, reviews = run_director(raw, raw)
    assert isinstance(result, c.QuestionRejected) and result.failure.failure.stage == "schema"
    assert len(calls) == 2 and reviews == []


@pytest.mark.parametrize("name", ["tech_lead", "hr_manager", "domain_lead"])
def test_one_director_accepts_each_controller_authorized_persona(
    plan, question, run_director, name
):
    result, _, _ = run_director(
        replace(question, persona=name), plan=replace(plan, allowed_personas=(name,))
    )
    assert isinstance(result, c.QuestionReady) and result.result.data.data.persona == name


def test_first_hr_question_needs_no_code_evidence(plan, question, run_director):
    contract = c.QuestionContract(
        "자기소개", (c.RequiredPoint("intro", "자기소개"),), (), (), "자기소개"
    )
    plan = replace(
        plan, question_id="question-1", turn=1, contract=contract, allowed_personas=("hr_manager",)
    )
    question = replace(
        question,
        persona="hr_manager",
        text="간단히 자기소개를 해 주시겠어요?",
        question_contract=contract,
    )
    result, calls, _ = run_director(question, plan=plan)
    assert isinstance(result, c.QuestionReady) and result.turn == 1
    assert json.loads(calls[0].input_json)["evidence"] == []


def test_conflicting_text_cannot_shadow_a_fixed_evidence_identity(plan, run_director):
    evidence = c.AnalysisEvidence("ev-1", "repo-1", "sha-fixed", "code", "a.py", "actual", None)
    with pytest.raises(c.ContractError):
        run_director(
            plan=replace(plan, contract=replace(plan.contract, basis_refs=("ev-1",))),
            evidence=(evidence,),
            evidence_refs=frozenset({"ev-1"}),
            basis_refs=frozenset({"ev-1"}),
            allowed_locations=frozenset({("repo-1", "sha-fixed", "a.py")}),
            reference_texts=(c.ReferenceText("ev-1", "contradictory replacement"),),
        )
