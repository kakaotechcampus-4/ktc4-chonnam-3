from itertools import combinations
from typing import get_args
from uuid import uuid4

import pytest
from devon_ai import contracts as c

from app.db.models import InterviewTurn


def contract(*keys):
    return c.QuestionContract(
        "purpose", (c.RequiredPoint("point", "description"),), (), (), "scope", keys
    )


def targets(contracts, allowed, has_jd=True):
    from app.features.interview.evaluation_coverage import plan_evaluation_targets

    return plan_evaluation_targets(contracts, allowed, has_jd=has_jd)


def test_first_hr_question_reserves_personal_role_and_communication():
    assert targets((), ("hr_manager",)) == (
        c.EvaluationTarget("hr_manager", ("contribution_clarity", "communication")),
    )


def test_presented_question_keys_control_the_next_primary_technical_target():
    history = (
        contract("contribution_clarity", "communication"),
        contract("project_understanding", "communication"),
    )
    assert targets(history, ("tech_lead",))[0].keys == ("technical_reasoning", "communication")


def test_domain_question_reserves_job_fit_only_until_that_opportunity_is_presented():
    first = contract("contribution_clarity", "communication")
    assert targets((first,), ("domain_lead",))[0].keys == ("company_job_fit", "communication")
    assert targets(
        (
            first,
            contract(
                "company_job_fit",
            ),
        ),
        ("domain_lead",),
    )[0].keys == ("communication",)


def test_legacy_first_question_does_not_gain_unasked_evaluation_keys():
    assert targets((contract(),), ("tech_lead", "domain_lead")) == ()


def test_missing_jd_cannot_become_a_job_fit_assumption():
    first = contract("contribution_clarity", "communication")
    assert targets((first,), ("domain_lead",), has_jd=False)[0].keys == ("communication",)


def test_follow_up_position_preserves_actual_parent_depth_and_turn():
    from app.features.interview.question_structure import question_position

    interview_id = uuid4()
    parent = InterviewTurn(
        id=uuid4(),
        interview_session_id=interview_id,
        persona="tech_lead",
        turn_no=3,
        depth=2,
        status="answered",
    )
    question = c.Question(
        "tech_lead", "question", "topic", contract(), (), (), "follow_up", str(parent.id)
    )
    assert question_position(question, parent, interview_id=interview_id, turn_no=4) == (3, 3)
    with pytest.raises(ValueError, match="question_parent_invalid"):
        question_position(question, parent, interview_id=uuid4(), turn_no=4)


@pytest.mark.parametrize("domain_positions", list(combinations(range(8), 2)))
def test_every_allowed_six_technical_two_domain_order_reserves_all_six_areas(domain_positions):
    presented = [contract("contribution_clarity", "communication")]
    for position in range(8):
        persona = "domain_lead" if position in domain_positions else "tech_lead"
        target = targets(tuple(presented), (persona,))[0]
        presented.append(contract(*target.keys))
    assert {key for item in presented for key in item.evaluation_keys} == set(
        get_args(c.ScoreKeyId)
    )


def test_declared_opportunities_reach_report_validation_without_persona_mapping_loss():
    from devon_ai.report_scores import compute_scores

    presented = []
    turns = []
    requirement = c.JDRequirement("jd-1", "API design", "required", "jd.text", ())
    order = ("hr_manager",) + ("tech_lead",) * 6 + ("domain_lead",) * 2
    for index, persona in enumerate(order, 1):
        target = targets(tuple(presented), (persona,))[0]
        asked = contract(*target.keys)
        presented.append(asked)
        turns.append(
            c.ScoreTurn(
                str(index),
                persona,
                "question",
                "모르겠습니다",
                asked,
                ("jd-1",) if "company_job_fit" in target.keys else (),
                (requirement,),
            )
        )
    judgments = c.ScoreJudgments(
        tuple(
            c.ScoreJudgment(turn.turn_id, key, 0)
            for turn in turns
            for key in c.score_candidate_keys(turn)
        )
    )
    result = compute_scores(c.validate_score_judgments(judgments, turns=tuple(turns)))
    assert dict(result.key_scores) == dict.fromkeys(get_args(c.ScoreKeyId), 0)
    assert result.total_score == 0


def test_document_processing_failure_is_explicit_in_context_limitations():
    from app.features.interview.agent_context import _document_limitations

    assert _document_limitations(
        {
            "document_claims_status": "failed",
            "document_claims_error_code": "ocr_failed",
        }
    ) == ("document_claims:failed:ocr_failed",)
    assert _document_limitations({"document_claims_status": "succeeded"}) == ()


def test_failed_domain_classification_is_not_a_confirmed_domain_label():
    from app.features.interview.agent_context import _domain_limitations

    assert _domain_limitations({"_domain_classification": {"status": "failed"}}) == (
        "domain_classification_failed:using_general_frame",
    )
    assert _domain_limitations({"_domain_classification": {"status": "succeeded"}}) == ()
