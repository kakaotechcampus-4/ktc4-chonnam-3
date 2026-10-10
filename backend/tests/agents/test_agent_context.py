"""순서를 강제하지 않고 첫 HR 포함 기술 6·도메인 2·HR 1을 지킨다."""

import itertools

import pytest

from app.features.interview import agent_context

QUOTA = {"tech_lead": 6, "domain_lead": 2, "hr_manager": 1}


def counts(tech=0, hr=0, domain=0):
    return {"tech_lead": tech, "hr_manager": hr, "domain_lead": domain}


@pytest.mark.parametrize(
    "values,turn_no,expected",
    [
        (counts(), 1, ("hr_manager",)),
        (counts(hr=1), 2, ("tech_lead", "domain_lead")),
        (counts(tech=6, hr=1), 8, ("domain_lead",)),
        (counts(domain=2, hr=1), 4, ("tech_lead",)),
        (counts(tech=5, domain=1, hr=1), 8, ("tech_lead", "domain_lead")),
        (counts(tech=6, domain=1, hr=1), 9, ("domain_lead",)),
        (counts(tech=5, domain=2, hr=1), 9, ("tech_lead",)),
    ],
)
def test_persona_candidates_preserve_exact_quotas_without_fixed_order(values, turn_no, expected):
    assert agent_context.allowed_personas(values, turn_no=turn_no, quota=QUOTA) == expected


@pytest.mark.parametrize(
    "values,turn_no",
    [
        (counts(hr=True), 2),
        (counts(tech=-1, hr=2), 2),
        (counts(hr=1.0), 2),
        ({"hr_manager": 1}, 2),
        ({**counts(hr=1), "unknown": 0}, 2),
        (counts(hr=1), 3),
        (counts(hr=1), 1),
        (counts(), 0),
        (counts(), True),
        (counts(tech=6, hr=3), 10),
        (counts(tech=7, hr=1), 9),
        (counts(hr=5), 6),
        (counts(tech=1), 2),
        (counts(hr=2), 3),
        (counts(domain=3, hr=1), 5),
        (counts(tech=5, domain=1, hr=2), 9),
    ],
)
def test_malformed_or_unrecoverable_persona_counts_are_rejected(values, turn_no):
    with pytest.raises(agent_context.AgentStateError) as exc:
        agent_context.allowed_personas(values, turn_no=turn_no, quota=QUOTA)
    assert exc.value.reason == "persona_counts_invalid"
    assert str(exc.value) == "persona_counts_invalid"


def test_all_and_only_28_fixed_allocation_orders_can_complete():
    completed = 0
    for sequence in itertools.product(("tech_lead", "hr_manager", "domain_lead"), repeat=8):
        values = counts(hr=1)
        for turn_no, persona in enumerate(sequence, start=2):
            if persona not in agent_context.allowed_personas(values, turn_no=turn_no, quota=QUOTA):
                break
            values[persona] += 1
        else:
            assert values == counts(tech=6, domain=2, hr=1)
            completed += 1
    assert completed == 28
