import pytest

from app.integrations.jd.base import PostingContent
from app.llm_tasks.jd_extract import (
    MAX_REQUIREMENTS,
    JdExtractionError,
    build_requirement_drafts,
)


def _posting(**overrides) -> PostingContent:
    defaults = dict(
        site_adapter="wanted",
        fetch_url="https://www.wanted.co.kr/wd/1",
        content_form="text",
        requirements=["Python 3년 이상", "RDBMS 경험"],
        preferred_points=["Redis 경험"],
        main_tasks=["결제 API 개발"],
        skill_tags=["Python", "Redis"],
    )
    defaults.update(overrides)
    return PostingContent(**defaults)


def test_maps_each_field_to_its_own_category_in_order():
    drafts = build_requirement_drafts(_posting())

    categories = [d.category for d in drafts]
    assert categories == ["required", "required", "preferred", "responsibility"]

    texts = [d.text for d in drafts]
    assert texts == [
        "Python 3년 이상",
        "RDBMS 경험",
        "Redis 경험",
        "결제 API 개발",
    ]

    # display_order 는 0부터 순차 증가
    assert [d.display_order for d in drafts] == [0, 1, 2, 3]


def test_preferred_never_becomes_required():
    """W5 완료 기준: 우대를 필수로 바꾸지 않음"""
    drafts = build_requirement_drafts(_posting())

    preferred_texts = {d.text for d in drafts if d.category == "preferred"}
    required_texts = {d.text for d in drafts if d.category == "required"}

    assert "Redis 경험" in preferred_texts
    assert "Redis 경험" not in required_texts


def test_tech_tags_are_uniform_across_rows():
    drafts = build_requirement_drafts(_posting())

    for draft in drafts:
        assert draft.tech_tags == ["Python", "Redis"]


def test_caps_at_max_requirements():
    many_requirements = [f"요건 {i}" for i in range(MAX_REQUIREMENTS + 10)]
    posting = _posting(requirements=many_requirements, preferred_points=[], main_tasks=[])

    drafts = build_requirement_drafts(posting)

    assert len(drafts) == MAX_REQUIREMENTS


def test_unstructured_posting_raises_extraction_error():
    posting = _posting(requirements=[], preferred_points=[], main_tasks=[])

    with pytest.raises(JdExtractionError) as exc_info:
        build_requirement_drafts(posting)

    assert exc_info.value.code == "extraction_failed"
