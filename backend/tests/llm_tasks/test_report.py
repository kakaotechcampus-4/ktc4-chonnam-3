"""report 어댑터: AI 출력 검증과 모듈 탐색. 실제 LLM은 호출하지 않는다. task-16"""

import copy

import pytest

from app.db.models.report import SCORE_KEYS
from app.llm_tasks import report as adapter
from app.llm_tasks.report import ReportDraftInvalidError, validate_draft

VALID = {
    "headline": "요약 한 줄",
    "summary": "종합 의견",
    "scores": {
        key: {"score": value, "reason": "근거", "evidence_turn_nos": [1]}
        for key, value in zip(SCORE_KEYS, (80, 70, 60, 90, 50, 100), strict=True)
    },
    "feedbacks": [
        {"persona": "tech_lead", "tags": ["a"], "strengths": ["s"], "improvements": ["i"]}
    ],
}


def _with(**changes):
    data = copy.deepcopy(VALID)
    data.update(changes)
    return data


def test_total_score_is_simple_average():
    assert validate_draft(VALID).total_score == 75.0


def test_total_score_rounds_to_two_decimals():
    data = copy.deepcopy(VALID)
    for key, value in zip(SCORE_KEYS, (10, 10, 10, 10, 10, 11), strict=True):
        data["scores"][key]["score"] = value
    assert validate_draft(data).total_score == 10.17


def test_boundary_scores_are_accepted():
    data = copy.deepcopy(VALID)
    data["scores"][SCORE_KEYS[0]]["score"] = 0
    data["scores"][SCORE_KEYS[1]]["score"] = 100
    assert validate_draft(data).scores[SCORE_KEYS[0]].score == 0


def test_missing_score_key_fails():
    data = copy.deepcopy(VALID)
    del data["scores"]["communication"]
    with pytest.raises(ReportDraftInvalidError, match="scores.keys"):
        validate_draft(data)


def test_extra_score_key_fails():
    data = copy.deepcopy(VALID)
    data["scores"]["bonus"] = {"score": 50}
    with pytest.raises(ReportDraftInvalidError, match="scores.keys"):
        validate_draft(data)


@pytest.mark.parametrize("bad", [-1, 100.5, None, "80", True, float("nan"), float("inf")])
def test_invalid_score_value_fails(bad):
    data = copy.deepcopy(VALID)
    data["scores"]["communication"]["score"] = bad
    with pytest.raises(ReportDraftInvalidError, match="communication.score"):
        validate_draft(data)


@pytest.mark.parametrize("field", ["headline", "summary"])
def test_blank_text_fails(field):
    with pytest.raises(ReportDraftInvalidError, match=field):
        validate_draft(_with(**{field: "  "}))


def test_unknown_or_duplicate_persona_fails():
    bad = [{"persona": "ceo", "tags": [], "strengths": [], "improvements": []}]
    with pytest.raises(ReportDraftInvalidError, match="persona"):
        validate_draft(_with(feedbacks=bad))
    dup = VALID["feedbacks"] * 2
    with pytest.raises(ReportDraftInvalidError, match="persona_duplicate"):
        validate_draft(_with(feedbacks=dup))


def test_non_mapping_output_fails():
    with pytest.raises(ReportDraftInvalidError):
        validate_draft("not json object")


def test_resolve_generator_without_ai_function_fails():
    # AI 모듈은 아직 docstring 뿐이라 generate_report 가 없다.
    with pytest.raises(adapter.ReportModuleUnavailableError):
        adapter.resolve_generator()
