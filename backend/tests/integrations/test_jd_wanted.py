import json

import httpx
import pytest

from app.integrations.jd.base import (
    PostingContentEmptyError,
    PostingFetchError,
    PostingUnreachableError,
    UnsupportedSiteError,
)
from app.integrations.jd.resolver import resolve_adapter
from app.integrations.jd.wanted import WantedAdapter, extract_job_id
from app.llm_tasks.jd_extract import build_requirement_drafts

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


def _mock_client(payload: object, status_code: int = 200) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        # json=None은 빈 본문이 되므로, JSON null도 검증하도록 직접 직렬화한다.
        return httpx.Response(
            status_code,
            content=json.dumps(payload),
            headers={"content-type": "application/json"},
        )

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


async def test_closed_posting_with_accessible_content_remains_analyzable():
    # 실제 마감 공고(250049)의 상태 필드. 채용 마감과 본문 수집 실패는 다르다.
    payload = {
        "job": {**FIXTURE_PAYLOAD["job"], "status": "close", "due_time": None, "hidden": True}
    }
    async with _mock_client(payload) as client:
        posting = await WantedAdapter(client=client).fetch(WANTED_URL)

    drafts = build_requirement_drafts(posting)
    assert posting.requirements == ["Python 3년 이상", "RDBMS 경험"]
    assert [draft.text for draft in drafts] == [
        "Python 3년 이상",
        "RDBMS 경험",
        "Redis 경험",
        "MSA 경험",
        "결제 API 개발",
        "정산 배치 운영",
    ]


async def test_closed_posting_without_content_is_still_a_fetch_failure():
    async with _mock_client({"job": {"status": "close", "detail": {}}}) as client:
        with pytest.raises(PostingContentEmptyError) as exc_info:
            await WantedAdapter(client=client).fetch(WANTED_URL)

    assert exc_info.value.code == "jd_fetch_failed"


async def test_fetch_empty_body_raises_content_empty():
    empty_payload = {"job": {"position": None, "detail": {}, "company": {}, "skill_tags": []}}
    adapter = WantedAdapter(client=_mock_client(empty_payload))

    with pytest.raises(PostingContentEmptyError):
        await adapter.fetch(WANTED_URL)


async def test_fetch_reads_position_from_detail_when_job_level_missing():
    """실제 응답(job id 380611, 2026-09-14 확인)엔 job.position/job.title 이 없고
    detail.position 에만 직무명이 들어있었음"""
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


@pytest.mark.parametrize(
    "url",
    [
        "https://www.wanted.co.kr/wd/123456oops",
        "https://www.wanted.co.kr/?next=https://www.wanted.co.kr/wd/123456",
        "https://www.wanted.co.kr/wd/123456/other",
        "https://wanted.co.kr/wd/123456;other",
        "https://wanted.co.kr:invalid/wd/123456",
        "https://wanted.co.kr:99999/wd/123456",
        "https://www.wanted.co.kr/wd/１２３４５６",
        "https://www.wanted.co.kr.evil.example/wd/123456",
        "https://evil.example/?next=https://www.wanted.co.kr/wd/123456",
        "ftp://www.wanted.co.kr/wd/123456",
        "https://[invalid/wd/123456",
    ],
)
async def test_invalid_posting_url_is_rejected_before_fetch(url):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=FIXTURE_PAYLOAD)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(UnsupportedSiteError):
            await WantedAdapter(client=client).fetch(url)
        with pytest.raises(UnsupportedSiteError):
            await resolve_adapter(url, client=client).fetch(url)

    assert requests == []


@pytest.mark.parametrize(
    "url",
    [
        WANTED_URL,
        "https://wanted.co.kr/wd/123456/",
        "https://WWW.WANTED.CO.KR/wd/123456?utm_source=share#detail",
        "http://wanted.co.kr/wd/123456?next=/wd/999999",
    ],
)
async def test_valid_posting_urls_fetch_the_path_id(url):
    requested_urls = []

    def handler(request):
        requested_urls.append(str(request.url))
        return httpx.Response(200, json=FIXTURE_PAYLOAD)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        posting = await resolve_adapter(url, client=client).fetch(url)

    assert requested_urls == ["https://www.wanted.co.kr/api/chaos/jobs/v1/123456/details"]
    assert posting.requirements == ["Python 3년 이상", "RDBMS 경험"]


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {"data": None},
        {"data": []},
        {"job": []},
        {"job": {"detail": []}},
        {"job": {"detail": {"requirements": ["Python"]}, "company": False}},
        {"job": {"detail": {"position": 123}}},
        {"job": {"detail": {"intro": ["소개"]}}},
        {
            "job": {
                "detail": {"requirements": ["Python"]},
                "company": {"name": {"text": "회사"}},
            }
        },
        {"job": {"detail": {"requirements": ["Python"]}, "company": {"industry_name": 123}}},
        {"job": {"detail": {"requirements": 123}}},
        {"job": {"detail": {"requirements": [None]}}},
        {"job": {"detail": {"requirements": ["Python", {"text": "Redis"}]}}},
        {"job": {"detail": {"preferred_points": [False]}}},
        {"job": {"detail": {"main_tasks": {"text": "API 개발"}}}},
        {"job": {"detail": {"requirements": ["Python"]}, "skill_tags": "Python"}},
        {"job": {"detail": {"requirements": ["Python"]}, "skill_tags": [None]}},
        {"job": {"detail": {"requirements": ["Python"]}, "skill_tags": [{"text": 123}]}},
        {"job": {"detail": {"requirements": ["Python"]}, "skill_tags": [{"name": "Python"}]}},
    ],
)
async def test_malformed_payload_is_a_fetch_failure(payload):
    async with _mock_client(payload) as client:
        with pytest.raises(PostingFetchError) as exc_info:
            await WantedAdapter(client=client).fetch(WANTED_URL)

    assert exc_info.value.code == "jd_fetch_failed"


async def test_nested_payload_and_optional_null_fields_remain_supported():
    payload = {
        "data": {
            "job": {
                "detail": {
                    "position": "백엔드 개발자",
                    "intro": None,
                    "requirements": None,
                    "preferred_points": None,
                    "main_tasks": [" API 개발 ", ""],
                },
                "company": None,
                "skill_tags": None,
            }
        }
    }
    async with _mock_client(payload) as client:
        posting = await WantedAdapter(client=client).fetch(WANTED_URL)

    assert posting.position == "백엔드 개발자"
    assert posting.main_tasks == ["API 개발"]
    assert posting.requirements == posting.preferred_points == posting.skill_tags == []
    assert posting.company_name is None
    assert posting.raw_text == "백엔드 개발자\nAPI 개발"


async def test_string_and_object_skill_tags_preserve_source_text():
    payload = {
        "job": {
            "detail": {"requirements": " Python 경험\n\nRedis 경험 "},
            "skill_tags": ["Python", {"text": "Redis"}, {"text": ""}],
        }
    }
    async with _mock_client(payload) as client:
        posting = await WantedAdapter(client=client).fetch(WANTED_URL)

    assert posting.requirements == ["Python 경험", "Redis 경험"]
    assert posting.skill_tags == ["Python", "Redis"]
