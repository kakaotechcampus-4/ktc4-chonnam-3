import pytest

from devon_ai import contracts as c
from devon_ai.report_scores import LEVEL_SCORES, _half_up, compute_scores

CONTRACT = c.QuestionContract("목적", (c.RequiredPoint("k", "내용"),), (), (), "평가 범위")
PERSONAS = [
    "hr_manager", "tech_lead", "tech_lead", "domain_lead", "tech_lead",
    "tech_lead", "domain_lead", "tech_lead", "tech_lead",
]  # fmt: skip
TURNS = tuple(
    c.ScoreTurn(f"turn-{n}", persona, "질문", "답변", CONTRACT)
    for n, persona in enumerate(PERSONAS, 1)
)


def scored(level_of):
    """level_of(turn_id, key) -> 단계 또는 "not_applicable"로 전체 판정을 만든다."""
    items = tuple(
        c.ScoreJudgment(t.turn_id, key, level_of(t.turn_id, key))
        for t in TURNS
        for key in c.SCORE_CANDIDATE_KEYS[t.persona]
    )
    return c.validate_score_judgments(c.ScoreJudgments(items), turns=TURNS)


def by_key(result):
    return dict(result.key_scores)


def test_level_scores_match_the_proposed_table():
    assert LEVEL_SCORES == {0: 0, 1: 20, 2: 45, 3: 70, 4: 90}


@pytest.mark.parametrize(
    ("numerator", "denominator", "expected"),
    [(65, 2, 33), (5, 2, 3), (1, 2, 1), (3, 2, 2), (49, 100, 0), (0, 5, 0)],
)
def test_half_up_rounds_point_five_up(numerator, denominator, expected):
    from fractions import Fraction

    assert _half_up(Fraction(numerator, denominator)) == expected
    # 파이썬 round()는 32.5를 32로 만든다. 이 함수가 따로 있는 이유다.
    assert round(32.5) == 32


def test_same_level_everywhere_gives_that_score():
    result = compute_scores(scored(lambda t, k: 4))
    assert set(by_key(result).values()) == {90}
    assert result.total_score == 90


def test_key_score_is_the_rounded_mean_of_its_turns():
    # technical_reasoning: 6개 tech 턴 중 3개는 1단계(20), 3개는 2단계(45) -> 32.5 -> 33
    low = {"turn-2", "turn-3", "turn-5"}

    def level(turn_id, key):
        if key == "technical_reasoning":
            return 1 if turn_id in low else 2
        return 2

    result = compute_scores(scored(level))
    assert by_key(result)["technical_reasoning"] == 33
    assert by_key(result)["communication"] == 45


def test_not_applicable_turns_are_left_out_of_the_mean():
    def level(turn_id, key):
        if key == "technical_reasoning" and turn_id in {"turn-2", "turn-3"}:
            return "not_applicable"
        return 3

    assert by_key(compute_scores(scored(level)))["technical_reasoning"] == 70


def test_total_is_the_rounded_mean_of_the_rounded_key_scores():
    # company_job_fit만 1단계(20), 나머지는 2단계(45): (5*45 + 20) / 6 = 40.83.. -> 41
    result = compute_scores(scored(lambda t, k: 1 if k == "company_job_fit" else 2))
    assert by_key(result)["company_job_fit"] == 20
    assert result.total_score == 41


def test_total_can_be_rebuilt_from_the_public_key_scores():
    # 세 key의 평균이 32.5(->33)이고 나머지는 20이면 key 평균으로 계산한 총점은 26이지만
    # 공개 점수 [33,33,33,20,20,20]의 평균 26.5는 27이어야 한다.
    low = {"turn-2", "turn-3", "turn-5"}
    mixed = {"project_understanding", "technical_reasoning", "problem_solving"}

    def level(turn_id, key):
        if key in mixed:
            return 1 if turn_id in low else 2
        return 1

    result = compute_scores(scored(level))
    scores = [score for _, score in result.key_scores]
    assert sorted(scores) == [20, 20, 20, 33, 33, 33]
    assert result.total_score == 27


def test_keys_come_back_in_public_order():
    keys = [key for key, _ in compute_scores(scored(lambda t, k: 2)).key_scores]
    assert keys == [
        "project_understanding",
        "technical_reasoning",
        "problem_solving",
        "communication",
        "contribution_clarity",
        "company_job_fit",
    ]


def test_an_unchecked_value_is_not_scored():
    with pytest.raises(c.ContractError):
        compute_scores(c.ScoreJudgments(()))  # type: ignore[arg-type]
