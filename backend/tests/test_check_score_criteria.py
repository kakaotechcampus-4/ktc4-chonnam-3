import pytest

from app.db.models.report import SCORE_KEYS
from scripts import check_score_criteria
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


@pytest.mark.parametrize(("ok", "code"), [(True, 0), (False, 1)])
def test_main_exit_code_follows_ok(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], ok: bool, code: int
) -> None:
    async def fake() -> dict[str, object]:
        return {"ok": ok}

    monkeypatch.setattr(check_score_criteria, "check", fake)
    assert check_score_criteria.main() == code
    assert '"ok"' in capsys.readouterr().out


def test_main_returns_1_when_connection_fails(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    async def boom() -> dict[str, object]:
        raise ConnectionError("db down")

    monkeypatch.setattr(check_score_criteria, "check", boom)
    assert check_score_criteria.main() == 1
    assert "점검 실패" in capsys.readouterr().out


@pytest.mark.parametrize("value", [None, "", "   ", 3, {"x": "y"}])
def test_non_text_rubric_values_are_reported(value: object) -> None:
    broken = {**GOOD[SCORE_KEYS[0]], "2": value}
    assert find_problems({**GOOD, SCORE_KEYS[0]: broken}) == [
        f"rubric text of {SCORE_KEYS[0]} levels ['2'] is not a non-empty string"
    ]
