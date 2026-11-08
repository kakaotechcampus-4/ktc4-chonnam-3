import pytest

from app.db.models.report import SCORE_KEYS
from scripts.check_score_criteria import LEVELS, find_problems
from scripts.seed_score_criteria import SCORE_CRITERIA

GOOD = {item.score_key: item.rubric for item in SCORE_CRITERIA}


def test_seed_rubrics_pass() -> None:
    assert find_problems(GOOD) == []


def test_missing_and_unexpected_keys_are_reported() -> None:
    active = {key: GOOD[key] for key in SCORE_KEYS[1:]} | {"other": GOOD[SCORE_KEYS[0]]}
    problems = find_problems(active)
    assert any("missing" in p and SCORE_KEYS[0] in p for p in problems)
    assert any("unexpected" in p and "other" in p for p in problems)


def test_bad_rubric_levels_are_reported() -> None:
    broken = dict(GOOD[SCORE_KEYS[0]])
    broken.pop(next(iter(LEVELS)))
    assert find_problems({**GOOD, SCORE_KEYS[0]: broken}) == [
        f"rubric levels of {SCORE_KEYS[0]} are not exactly 0..4"
    ]
    assert find_problems({**GOOD, SCORE_KEYS[0]: "text"})


@pytest.mark.parametrize("value", [None, "", "   ", 3, {"x": "y"}])
def test_non_text_rubric_values_are_reported(value: object) -> None:
    broken = {**GOOD[SCORE_KEYS[0]], "2": value}
    assert find_problems({**GOOD, SCORE_KEYS[0]: broken}) == [
        f"rubric text of {SCORE_KEYS[0]} levels ['2'] is not a non-empty string"
    ]
