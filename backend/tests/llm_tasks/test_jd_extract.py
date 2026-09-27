import pytest

from app.db.models.posting import JD_CATEGORIES
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

    # category는 API 표시와 DB 저장에 그대로 쓰이고, source_field로 원문 출처를 보존한다.
    assert [d.source_field for d in drafts] == [
        "requirements",
        "requirements",
        "preferred_points",
        "main_tasks",
    ]

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


def test_main_tasks_only_remains_analyzable_without_becoming_required():
    drafts = build_requirement_drafts(_posting(requirements=[], preferred_points=[]))

    assert len(drafts) == 1
    assert drafts[0].text == "결제 API 개발"
    assert drafts[0].source_field == "main_tasks"
    assert drafts[0].category == "responsibility"


def test_tech_tags_are_uniform_across_rows():
    drafts = build_requirement_drafts(_posting())

    for draft in drafts:
        assert draft.tech_tags == ["Python", "Redis"]


def test_caps_at_max_requirements():
    many_requirements = [f"요건 {i}" for i in range(MAX_REQUIREMENTS + 10)]
    posting = _posting(requirements=many_requirements, preferred_points=[], main_tasks=[])

    drafts = build_requirement_drafts(posting)

    assert len(drafts) == MAX_REQUIREMENTS


def test_category_matches_db_check_constraint():
    """이슈 #63: category 값 집합이 jd_requirements.category CHECK 제약과 갈라지면 안 됨."""
    drafts = build_requirement_drafts(_posting())

    assert {d.category for d in drafts} <= set(JD_CATEGORIES)


def test_unstructured_posting_raises_extraction_error():
    posting = _posting(requirements=[], preferred_points=[], main_tasks=[])

    with pytest.raises(JdExtractionError) as exc_info:
        build_requirement_drafts(posting)

    assert exc_info.value.code == "jd_extraction_failed"


def test_leading_bullets_are_stripped_and_bullet_only_lines_dropped():
    drafts = build_requirement_drafts(
        _posting(
            requirements=["• Python 3년 이상", "∘ 하위 항목", "- RDBMS 경험", "•"],
            preferred_points=[],
            main_tasks=[],
        )
    )

    assert [d.text for d in drafts] == ["Python 3년 이상", "하위 항목", "RDBMS 경험"]


def test_cap_keeps_all_required_then_alternates_preferred_and_main_tasks():
    """필수 요건을 먼저 담고, 우대가 길어도 주요 업무가 통째로 잘리지 않는다."""
    posting = _posting(
        requirements=[f"요건 {i}" for i in range(12)],
        preferred_points=[f"우대 {i}" for i in range(12)],
        main_tasks=[f"업무 {i}" for i in range(15)],
    )

    drafts = build_requirement_drafts(posting)

    assert len(drafts) == MAX_REQUIREMENTS
    counts = {c: sum(d.category == c for d in drafts) for c in JD_CATEGORIES}
    # 필수 12개를 모두 담고 남은 8자리를 우대·업무가 4개씩 나눈다.
    assert counts == {"required": 12, "preferred": 4, "responsibility": 4}
    # 카테고리별 원문 앞부분이 남고 표시 순서는 연속이다.
    assert [d.text for d in drafts if d.category == "preferred"] == [f"우대 {i}" for i in range(4)]
    assert [d.display_order for d in drafts] == list(range(MAX_REQUIREMENTS))


def test_short_category_leaves_its_share_to_the_other():
    posting = _posting(
        requirements=[f"요건 {i}" for i in range(4)],
        preferred_points=[f"우대 {i}" for i in range(20)],
        main_tasks=["업무 0", "업무 1"],
    )

    counts = {c: 0 for c in JD_CATEGORIES}
    for d in build_requirement_drafts(posting):
        counts[d.category] += 1

    assert counts == {"required": 4, "preferred": 14, "responsibility": 2}
