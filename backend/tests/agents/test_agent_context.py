"""남은 턴에서 최소 Persona 배분을 지킬 수 있는 후보만 허용한다."""

import itertools

import pytest

from app.features.interview import agent_context


def counts(tech=0, hr=0, domain=0):
    return {"tech_lead": tech, "hr_manager": hr, "domain_lead": domain}


@pytest.mark.parametrize(
    "values,turn_no,expected",
    [
        (counts(), 1, ("hr_manager",)),
        (counts(hr=1), 2, ("tech_lead", "hr_manager", "domain_lead")),
        (counts(tech=4, hr=4), 9, ("tech_lead",)),
        (counts(tech=6, hr=2), 9, ("hr_manager", "domain_lead")),
        (counts(tech=5, hr=3), 9, ("tech_lead", "hr_manager", "domain_lead")),
        (counts(tech=3, hr=4), 8, ("tech_lead",)),
        (counts(tech=6, hr=1), 8, ("hr_manager", "domain_lead")),
    ],
)
def test_persona_candidates_preserve_minima_without_forcing_six_technical_turns(
    values, turn_no, expected
):
    assert agent_context.allowed_personas(values, turn_no=turn_no) == expected


def test_missing_domain_frames_still_allows_hr_to_meet_combined_minimum():
    assert agent_context.allowed_personas(
        counts(tech=6, hr=2), turn_no=9, domain_available=False
    ) == ("hr_manager",)


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
    ],
)
def test_malformed_or_unrecoverable_persona_counts_are_rejected(values, turn_no):
    with pytest.raises(agent_context.AgentStateError) as exc:
        agent_context.allowed_personas(values, turn_no=turn_no)
    assert exc.value.reason == "persona_counts_invalid"
    assert str(exc.value) == "persona_counts_invalid"


def test_every_reachable_nine_turn_sequence_meets_both_minima():
    for sequence in itertools.product(("tech_lead", "hr_manager", "domain_lead"), repeat=8):
        values = counts(hr=1)
        for turn_no, persona in enumerate(sequence, start=2):
            if persona not in agent_context.allowed_personas(values, turn_no=turn_no):
                break
            values[persona] += 1
        else:
            assert values["tech_lead"] >= 5
            assert values["hr_manager"] + values["domain_lead"] >= 3
