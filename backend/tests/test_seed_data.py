"""score_criteria 시드 데이터 자체의 완결성 검증 (DB 불필요, task-03)."""

from app.shared.enums import ScoreKey
from scripts.seed_score_criteria import SCORE_CRITERIA


def test_score_criteria_covers_every_score_key_exactly_once() -> None:
    keys = [criterion.score_key for criterion in SCORE_CRITERIA]
    assert sorted(keys) == sorted(key.value for key in ScoreKey)
    assert len(keys) == len(set(keys))


def test_score_criteria_display_order_is_unique_and_dense() -> None:
    orders = sorted(criterion.display_order for criterion in SCORE_CRITERIA)
    assert orders == list(range(1, len(SCORE_CRITERIA) + 1))


def test_score_criteria_have_non_empty_label_and_rubric() -> None:
    for criterion in SCORE_CRITERIA:
        assert criterion.label_ko.strip()
        assert criterion.description.strip()
        assert len(criterion.rubric) >= 3
