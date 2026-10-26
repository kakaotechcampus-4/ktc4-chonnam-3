"""score_criteria / domain_question_frames 시드 데이터 자체의 완결성 검증 (DB 불필요, task-03)."""

from app.shared.enums import ScoreKey
from scripts.seed_domain_question_frames import DOMAIN_QUESTION_FRAMES
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


def test_domain_question_frames_has_three_axes_per_domain() -> None:
    from app.db.models.knowledge import QUESTION_FRAME_AXES
    from app.db.models.posting import DOMAIN_CATEGORIES

    by_domain: dict[str, set[str]] = {}
    for frame in DOMAIN_QUESTION_FRAMES:
        by_domain.setdefault(frame.domain_category, set()).add(frame.axis)

    assert set(by_domain) == set(DOMAIN_CATEGORIES)
    for domain, axes in by_domain.items():
        assert axes == set(QUESTION_FRAME_AXES), f"{domain} missing axes: {axes}"


def test_domain_question_frames_no_duplicate_domain_axis_pairs() -> None:
    pairs = [(frame.domain_category, frame.axis) for frame in DOMAIN_QUESTION_FRAMES]
    assert len(pairs) == len(set(pairs))


def test_domain_question_frames_have_non_empty_text() -> None:
    for frame in DOMAIN_QUESTION_FRAMES:
        assert frame.frame_text.strip()


def test_domain_question_frames_are_hypothetical_questions() -> None:
    # 사용자가 해당 도메인 경험이 있다고 전제하지 않는 가정형 질문이어야 한다.
    for frame in DOMAIN_QUESTION_FRAMES:
        assert frame.frame_text.endswith("시겠어요?"), frame.frame_text
        assert "물어본다" not in frame.frame_text


def test_score_criteria_level_one_requires_a_question_or_answer() -> None:
    # 질문하지 않은 항목(미관찰)이 1단계로 읽히지 않아야 한다 (task-11).
    for criterion in SCORE_CRITERIA:
        level_one = criterion.rubric["1"]
        assert "질문" in level_one or "답변" in level_one, criterion.score_key
