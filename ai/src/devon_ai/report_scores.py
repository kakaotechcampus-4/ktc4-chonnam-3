"""검증된 단계 판정에서 공개 점수를 계산한다(LLM 없음).

환산표와 반올림은 이 파일의 상수·함수로만 정한다.
"""

from dataclasses import dataclass
from fractions import Fraction
from typing import get_args

from devon_ai import contracts as c

# 단계 → 점수. 0단계는 "질문을 받고도 답하지 못함"에만 쓴다(backend seed_score_criteria와 같은 값).
LEVEL_SCORES: dict[int, int] = {0: 0, 1: 20, 2: 45, 3: 70, 4: 90}


@dataclass(frozen=True)
class ReportScores:
    """key별 점수(공개 순서)와 totalScore. 모두 0~100 정수다."""

    key_scores: tuple[tuple[c.ScoreKeyId, int], ...]
    total_score: int


def _half_up(value: Fraction) -> int:
    """파이썬 round()의 짝수 반올림 대신 .5를 올린다."""
    return (2 * value.numerator + value.denominator) // (2 * value.denominator)


def compute_scores(checked: c.ContractChecked[c.ScoreJudgments]) -> ReportScores:
    """key별로 not_applicable을 뺀 단계 점수의 평균을 half-up 정수로 만든다.

    totalScore는 그 정수 6개의 평균을 half-up한 값이다.

    공개되는 key 점수만으로 totalScore를 재현할 수 있다(BE 총점 계산과 같은 규칙).
    """
    if type(checked) is not c.ContractChecked or type(checked.data) is not c.ScoreJudgments:
        raise c.ContractError("schema", "checked score judgments")
    key_scores: list[tuple[c.ScoreKeyId, int]] = []
    for key in get_args(c.ScoreKeyId):
        scores = [
            LEVEL_SCORES[item.level]
            for item in checked.data.judgments
            if item.key == key and item.level != "not_applicable"
        ]
        if not scores:  # 검증기가 막지만 기본 점수를 만들지 않으려고 한 번 더 확인한다.
            raise c.ContractError("semantic", "unscorable key")
        key_scores.append((key, _half_up(Fraction(sum(scores), len(scores)))))
    return ReportScores(
        tuple(key_scores), _half_up(Fraction(sum(v for _, v in key_scores), len(key_scores)))
    )
