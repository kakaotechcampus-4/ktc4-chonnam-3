"""이미지 공고 요구사항은 실제 전사와 분류 제목에 근거해야 한다."""

import importlib

import pytest

from devon_ai import contracts as c


def parse(item, blocks=None):
    name = "devon_ai.llm_tasks.jd_extract_image"
    assert importlib.util.find_spec(name) is not None, "이미지 JD 검증 경계가 필요하다"
    module = importlib.import_module(name)
    return module.parse_image_requirements(
        {"requirements": [item], "limitations": []}, blocks or {"B1": "우대사항\nRedis 경험"}
    )


def item(**updates):
    return {
        "category": "preferred",
        "text": "Redis 경험",
        "tech_tags": ["Redis"],
        "source_ids": ["B1"],
        **updates,
    }


def test_transcribed_preferred_requirement_retains_actual_source():
    result = parse(item())
    assert result.requirements[0].category == "preferred"
    assert result.requirements[0].source_ids == ("B1",)


@pytest.mark.parametrize(
    "updates",
    [
        {"category": "required"},
        {"source_ids": ["unknown"]},
        {"text": "Redis 운영 성과"},
        {"tech_tags": ["Kubernetes"]},
    ],
)
def test_unsupported_requirement_is_rejected_without_discarding_source(updates):
    result = parse(item(**updates))
    assert result.requirements == () and result.rejected


@pytest.mark.parametrize("updates", [{"source_ids": "B1"}, {"category": []}])
def test_schema_error_is_distinct_from_semantic_rejection(updates):
    with pytest.raises(c.ContractError) as caught:
        parse(item(**updates))
    assert caught.value.stage == "schema"


def test_technology_name_must_not_be_a_substring_of_another_name():
    result = parse(
        item(text="Google Cloud 경험", tech_tags=["Go"]), {"B1": "우대사항\nGoogle Cloud 경험"}
    )
    assert result.requirements == () and result.rejected
