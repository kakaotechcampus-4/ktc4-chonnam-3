"""prompt 본문이 코드가 기대하는 필드와 어긋나지 않는지 확인한다. 모델 품질은 검사하지 않는다."""

import dataclasses
from pathlib import Path

import pytest

from devon_ai import contracts as c

PROMPTS = Path(__file__).resolve().parents[1] / "prompts"


def read(name: str) -> str:
    return (PROMPTS / name).read_text(encoding="utf-8")


def names(contract_type: type) -> list[str]:
    return [item.name for item in dataclasses.fields(contract_type)]


def test_score_prompt_names_every_output_and_input_field_the_code_uses():
    text = read("report-score-v1.md")
    required = [
        "ScoreJudgments",
        "judgments",
        "not_applicable",
        "turns",
        "rubric",
        "candidate_keys",
    ]
    required += ["question_contract", "evaluation_scope", "turn_id", "key", "level"]
    required += names(c.QuestionContract)[:2]  # purpose, required_points
    assert [word for word in required if word not in text] == []


def test_narrative_prompt_names_every_output_and_input_field_the_code_uses():
    text = read("report-runtime-v4.md")  # 현재 runtime prompt. v1은 기준선으로 보존한다.
    required = ["ReportNarrative", "headline", "summary", "persona_feedbacks"]
    required += names(c.SummaryNarrative) + names(c.PersonaNarrative) + names(c.NarrativeClaim)
    required += ["turn_id", "follows", "evidence_refs", "tool_results", "analysis", "evidence_id"]
    required += list(c.NARRATIVE_PERSONAS)
    required += ["found", "not_found", "insufficient_analysis", "tool_error"]
    assert [word for word in required if word not in text] == []


@pytest.mark.parametrize("name", ["report-score-v1.md", "report-v1.md"])
def test_prompts_treat_input_text_as_data_and_forbid_extra_output(name):
    text = read(name)
    assert "지시" in text and "추가 필드" in text and "마크다운" in text


def test_narrative_prompt_limits_match_the_validator():
    text = read("report-v1.md")
    # 코드는 headline 100자, tags 3개·20자를 검사하고 prompt는 headline을 더 짧게 요구한다.
    assert "60자" in text and "20자" in text and "1~3개" in text
    assert c.HEADLINE_MAX_CHARS >= 60 and c.TAG_MAX_CHARS == 20
