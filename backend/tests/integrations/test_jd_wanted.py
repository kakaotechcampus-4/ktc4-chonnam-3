import httpx
import pytest

from app.integrations.jd.base import PostingContentEmptyError, PostingUnreachableError
from app.integrations.jd.wanted import WantedAdapter, extract_job_id

WANTED_URL = "https://www.wanted.co.kr/wd/123456"

FIXTURE_PAYLOAD = {
    "job": {
        "position": "백엔드 개발자 (Python/Django)",
        "detail": {
            "intro": "저희 팀은 결제 시스템을 만듭니다.",
            "main_tasks": ["결제 API 개발", "정산 배치 운영"],
            "requirements": ["Python 3년 이상", "RDBMS 경험"],
            "preferred_points": ["Redis 경험", "MSA 경험"],
        },
        "company": {"name": "테스트컴퍼니", "industry_name": "핀테크"},
        "skill_tags": [{"text": "Python"}, {"text": "Django"}, {"text": "Redis"}],
    }
}


def _mock_client(payload: dict | None, status_code: int = 200) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if payload is None:
            return httpx.Response(status_code)
        return httpx.Response(status_code, json=payload)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_extract_job_id_from_wanted_url():
    assert extract_job_id(WANTED_URL) == "123456"
    assert extract_job_id("https://example.com") is None


async def test_fetch_parses_structured_fields():
    adapter = WantedAdapter(client=_mock_client(FIXTURE_PAYLOAD))

    posting = await adapter.fetch(WANTED_URL)

    assert posting.site_adapter == "wanted"
    assert posting.content_form == "text"
    assert posting.position == "백엔드 개발자 (Python/Django)"
    assert posting.company_name == "테스트컴퍼니"
    assert posting.industry == "핀테크"
    assert posting.requirements == ["Python 3년 이상", "RDBMS 경험"]
    assert posting.preferred_points == ["Redis 경험", "MSA 경험"]
    assert posting.main_tasks == ["결제 API 개발", "정산 배치 운영"]
    assert posting.skill_tags == ["Python", "Django", "Redis"]
    assert posting.is_structured is True


async def test_fetch_404_raises_unreachable():
    adapter = WantedAdapter(client=_mock_client(None, status_code=404))

    with pytest.raises(PostingUnreachableError):
        await adapter.fetch(WANTED_URL)


async def test_fetch_empty_body_raises_content_empty():
    empty_payload = {"job": {"position": None, "detail": {}, "company": {}, "skill_tags": []}}
    adapter = WantedAdapter(client=_mock_client(empty_payload))

    with pytest.raises(PostingContentEmptyError):
        await adapter.fetch(WANTED_URL)


async def test_fetch_reads_position_from_detail_when_job_level_missing():
    """실제 응답(job id 380611, 2026-09-14 확인)엔 job.position/job.title 이 없고
    detail.position 에만 직무명이 들어있었다."""
    payload = {
        "job": {
            "position": None,
            "title": None,
            "detail": {
                "position": "Product Designer (B2B/광고플랫폼)",
                "intro": "",
                "main_tasks": ["광고플랫폼 개선"],
                "requirements": ["디자인 경력 5년 이상"],
                "preferred_points": [],
            },
            "company": {"name": "테스트", "industry_name": None},
            "skill_tags": [],
        }
    }
    adapter = WantedAdapter(client=_mock_client(payload))

    posting = await adapter.fetch(WANTED_URL)

    assert posting.position == "Product Designer (B2B/광고플랫폼)"


async def test_fetch_accepts_single_string_fields_not_only_lists():
    payload = {
        "job": {
            "position": "프론트엔드 개발자",
            "detail": {
                "intro": "",
                "main_tasks": "화면 개발\n컴포넌트 설계",
                "requirements": "React 경험",
                "preferred_points": "",
            },
            "company": {"name": "테스트", "industry_name": None},
            "skill_tags": [],
        }
    }
    adapter = WantedAdapter(client=_mock_client(payload))

    posting = await adapter.fetch(WANTED_URL)

    assert posting.main_tasks == ["화면 개발", "컴포넌트 설계"]
    assert posting.requirements == ["React 경험"]
    assert posting.preferred_points == []
