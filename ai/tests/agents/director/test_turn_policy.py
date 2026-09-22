from itertools import product

import pytest

from devon_ai import contracts as c
from devon_ai.agents.director import turn_policy as policy

HR, TECH, DOMAIN = "hr_manager", "tech_lead", "domain_lead"


@pytest.mark.parametrize(
    ("presented", "expected"),
    [
        ((), {HR}),
        ((HR,), {TECH, HR, DOMAIN}),
        ((HR,) * 4, {TECH}),
        ((HR,) + (TECH,) * 6, {HR, DOMAIN}),
        ((HR, DOMAIN, HR) + (TECH,) * 5, {TECH, HR, DOMAIN}),
        ((HR, DOMAIN, HR) + (TECH,) * 6, set()),
        ((HR,) * 4 + (TECH,) * 5, set()),
    ],
)
def test_candidate_feasibility_and_flexible_hr(presented, expected):
    assert set(policy.allowed_personas(presented)) == expected


@pytest.mark.parametrize(
    "presented",
    [[], (TECH,), ("manager",), (HR,) * 5, (HR,) + (TECH,) * 7, (HR,) * 10, (True,)],
)
def test_invalid_or_already_impossible_history_is_rejected(presented):
    with pytest.raises(c.ContractError):
        policy.allowed_personas(presented)


def test_every_allowed_path_can_finish_and_no_feasible_choice_is_removed():
    # Independent oracle: enumerate final schedules satisfying only the FIX rules.
    expected = {}
    for rest in product((TECH, HR, DOMAIN), repeat=8):
        schedule = (HR, *rest)
        if schedule.count(TECH) not in (5, 6):
            continue
        for length in range(9):
            expected.setdefault(schedule[:length], set()).add(schedule[length])
        expected[schedule] = set()
    for prefix, choices in expected.items():
        assert set(policy.allowed_personas(prefix)) == choices
