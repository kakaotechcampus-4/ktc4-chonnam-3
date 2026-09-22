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
