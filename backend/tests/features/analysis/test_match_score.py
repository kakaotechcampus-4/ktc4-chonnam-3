"""공고 전체 태그를 경력 충족이나 모든 요구사항의 근거로 확대하지 않는다."""

import uuid

import pytest

from app.db.models.posting import JdRequirement
from app.features.analysis.pipeline.steps.match_score import match_technologies


def requirement(text: str) -> JdRequirement:
    return JdRequirement(id=uuid.uuid4(), text=text, tech_tags=["Python", "Java"])


def test_matches_only_explicit_technology_and_requirement_text() -> None:
    python = requirement("Python 개발 경력 3년 이상")
    unrelated = requirement("협업 경험과 원활한 의사소통")
    result = match_technologies(
        [" Python ", "PYTHON", "Java"], ["python", "JavaScript"], [python, unrelated]
    )
    assert result.technologies == ("Python",)
    assert result.requirement_ids == (python.id,)
    assert result.reason == "공고와 관련된 기술: Python"


@pytest.mark.parametrize(
    ("tags", "stack"), [([], ["Python"]), (["Python"], []), (["Java"], ["JavaScript"])]
)
def test_empty_or_unmatched_is_normal_non_recommendation(tags: list[str], stack: list[str]) -> None:
    result = match_technologies(tags, stack, [requirement("Python 개발")])
    assert result.technologies == ()
    assert result.requirement_ids == ()
    assert result.reason is None


@pytest.mark.parametrize(
    ("technology", "text", "matches"),
    [
        ("Java", "JavaScript 경험", False),
        ("Java", "Java/Spring 경험", True),
        ("C", "C++ 또는 C#", False),
        ("C++", "C++ 개발", True),
        ("C#", "C#을 사용한 개발", True),
        ("Node.js", "NodeXjs 개발", False),
        ("Node.js", "Node.js 개발", True),
        ("Go", "go to market 전략", False),
        ("Go", "Go를 활용한 서버 개발", True),
    ],
)
def test_requirement_technology_boundaries(technology: str, text: str, matches: bool) -> None:
    item = requirement(text)
    result = match_technologies([technology], [technology], [item])
    assert bool(result.requirement_ids) is matches
    # 문장 근거가 없어도 공고 전체 태그와의 기술 관련성은 남긴다.
    assert result.technologies == (technology,)
