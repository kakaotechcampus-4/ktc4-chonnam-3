"""Wanted 어댑터 — URL 판정/정규화와 구조화 필드 추출 (LLM 없음)."""

import pytest

from app.integrations.jd.base import JdUnsupportedSite
from app.integrations.jd.resolver import is_supported, normalize_posting_url, resolve_adapter
from app.integrations.jd.wanted import WantedAdapter

DETAIL_PAYLOAD = {
    "data": {
        "id": 123456,
        "position": "백엔드 개발자",
        "company": {"id": 7, "name": "토스뱅크"},
        "skill_tags": [{"id": 1, "title": "Redis"}, {"id": 2, "title": "Java"}],
        "detail": {
            "intro": "결제 플랫폼 팀입니다.",
            "main_tasks": "- 결제 API 개발",
            "requirements": "- Redis 등 캐시 시스템 운영 경험\n- Java 실무 경험 3년 이상",
            "preferred_points": "• 대용량 트래픽 처리 경험",
            "benefits": "- 점심 제공",
        },
    }
}


def test_matches_and_normalize() -> None:
    adapter = WantedAdapter()
    assert adapter.matches("https://www.wanted.co.kr/wd/123456?ref=search")
    assert not adapter.matches("https://www.saramin.co.kr/zf_user/jobs/view?rec_idx=1")
    assert (
        adapter.normalize("https://www.wanted.co.kr/wd/123456?ref=search")
        == "https://www.wanted.co.kr/wd/123456"
    )


def test_unsupported_site_is_blocked() -> None:
    assert is_supported("https://www.wanted.co.kr/wd/1") is True
    assert is_supported("https://www.jobkorea.co.kr/Recruit/GI_Read/1") is False
    with pytest.raises(JdUnsupportedSite):
        normalize_posting_url("https://example.com/job/1")


def test_extract_requirements_splits_required_and_preferred() -> None:
    adapter = WantedAdapter()
    posting = adapter._to_posting("123456", "https://api", DETAIL_PAYLOAD)
    assert posting.position == "백엔드 개발자"
    assert posting.company_name == "토스뱅크"
    assert posting.skill_tags == ["Redis", "Java"]

    items = adapter.extract_requirements(posting)
    kinds = [item.requirement_type for item in items]
    assert kinds == ["required", "required", "preferred"]
    assert items[0].text == "Redis 등 캐시 시스템 운영 경험"
    assert items[0].tech_tags == ["Redis"]
    # main_tasks/benefits 는 요구사항이 아니므로 들어가지 않는다.
    assert all("점심" not in item.text for item in items)


def test_resolve_adapter_returns_wanted() -> None:
    adapter = resolve_adapter("https://www.wanted.co.kr/wd/999")
    assert adapter.name == "wanted"
