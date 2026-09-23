"""Wanted 공고 수집과 어댑터 선택.

spec/backend/features/analysis-run.md / task-09

아래 fixture 는 /api/chaos/jobs/v1/{id}/details 를 실제로 호출해 확인한 구조다 (2026-09-21).
키 이름과 중첩은 실제 응답 그대로이고 본문 문구만 짧게 바꿨다 — 남의 공고 원문을
저장소에 넣지 않으려는 것이다. 구조가 바뀌면 이 파일과 wanted.py docstring 을 함께 고친다.
"""

from collections.abc import Callable
from typing import Any

import httpx
import pytest

from app.integrations.jd.base import (
    JD_ERROR_FETCH_FAILED,
    JD_ERROR_NOT_A_JOB_POSTING,
    JD_ERROR_UNSUPPORTED_SITE,
    JdFetchResult,
    JdParseStatus,
)
from app.integrations.jd.generic import GenericAdapter
from app.integrations.jd.resolver import (
    fetch_job_posting,
    normalize_posting_url,
    resolve_adapter,
)
from app.integrations.jd.wanted import WantedAdapter
from app.shared.enums import JdCategory

# 실제 응답 구조: data 래퍼가 없고 position 은 job.detail 안에 있다.
WANTED_DETAILS: dict[str, Any] = {
    "application": None,
    "job": {
        "id": 999,
        "status": "close",
        "due_time": "2026-10-20T00:00:00",
        "detail": {
            "id": 1234,
            "position": "백엔드 개발자",
            "intro": "회사 소개",
            "main_tasks": "• API 설계\n• 성능 개선",
            "requirements": "• Python 3년\n• RDB 경험",
            "preferred_points": "• 대용량 트래픽 경험\n1) Kubernetes",
            "benefits": "식대 지원",
            "hire_rounds": None,
        },
        "company": {
            "id": 2569,
            "name": "데본",
            "industry_name": "IT, 컨텐츠",
            # company_tags 는 title 키를 쓴다. skill_tags 와 형태가 다르다.
            "company_tags": [{"tag_type_id": 10025, "title": "연봉상위11~20%"}],
        },
        # ⚠ skill_tags 항목의 키는 text 다. title 이 아니다.
        "skill_tags": [
            {"tag_type_id": 1411, "text": "Python"},
            {"tag_type_id": 1412, "text": "FastAPI"},
            {"tag_type_id": 1413, "text": "PostgreSQL"},
        ],
        "attraction_tags": [{"tag_type_id": 10437, "title": "식대지원"}],
        "category_tag": {
            "parent_tag": {"id": 518, "text": "개발"},
            "child_tags": [{"id": 669, "text": "백엔드 개발자"}],
        },
        "name": None,
    },
}

# 없는 공고의 실제 404 본문.
JOB_NOT_FOUND_BODY: dict[str, Any] = {
    "error_code": 11001,
    "message": "job not found exception",
    "data": None,
}


async def _fetch(
    handler: Callable[[httpx.Request], httpx.Response],
    url: str = "https://www.wanted.co.kr/wd/999",
) -> JdFetchResult:
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        return await WantedAdapter(client=client).fetch(url)


# ── 실제 응답 구조 고정 ────────────────────────────────


def test_fixture_matches_verified_envelope() -> None:
    """fixture 가 실제 응답 구조에서 벗어나면 파서 테스트가 의미를 잃는다."""
    assert set(WANTED_DETAILS) == {"application", "job"}, "data 래퍼는 없다"

    job = WANTED_DETAILS["job"]
    assert "position" in job["detail"], "position 은 job.detail 안이다"
    assert "position" not in job, "job 바로 아래에 position 은 없다"
    assert "name" in job["company"]
    assert all("text" in tag for tag in job["skill_tags"]), "skill_tags 항목 키는 text 다"


# ── URL 판정·정규화 ────────────────────────────────────


@pytest.mark.parametrize(
    "url",
    [
        "https://www.wanted.co.kr/wd/123456",
        "https://wanted.co.kr/wd/123456?utm_source=x#top",
        "www.wanted.co.kr/wd/123456/",
    ],
)
def test_normalized_url_is_stable(url: str) -> None:
    """job_postings 재사용 키라서 같은 공고가 다른 행이 되면 안 된다."""
    assert WantedAdapter().normalize_url(url) == "https://www.wanted.co.kr/wd/123456"


@pytest.mark.parametrize(
    "url",
    [
        "https://www.wanted.co.kr/company/1234",
        "https://www.saramin.co.kr/zf_user/jobs/view?id=1",
        "https://example.com",
    ],
)
def test_non_wanted_urls_are_not_supported(url: str) -> None:
    assert WantedAdapter().supports(url) is False
    assert WantedAdapter().normalize_url(url) is None


# ── 성공 ───────────────────────────────────────────────


async def test_wanted_success() -> None:
    result = await _fetch(lambda request: httpx.Response(200, json=WANTED_DETAILS))

    assert result.status is JdParseStatus.SUCCEEDED
    assert result.adapter == "wanted"
    payload = result.payload
    assert payload is not None
    assert payload.position == "백엔드 개발자"
    assert payload.company_name == "데본"
    assert payload.source_posting_id == "999"
    assert payload.fetch_url == "https://www.wanted.co.kr/api/chaos/jobs/v1/999/details"


async def test_skill_tags_are_read_from_text_key() -> None:
    """실제 응답의 skill_tags 는 {"tag_type_id", "text"} 다.

    title 만 보던 때는 항상 빈 목록이 나왔다. skill_tags 가 tech_tags 원천이라
    조용히 비면 매칭이 통째로 망가진다.
    """
    result = await _fetch(lambda request: httpx.Response(200, json=WANTED_DETAILS))
    payload = result.payload
    assert payload is not None

    assert payload.skill_tags == ["Python", "FastAPI", "PostgreSQL"]


async def test_attraction_and_company_tags_are_not_mixed_into_skill_tags() -> None:
    """attraction_tags·company_tags 도 태그 모양이지만 skill_tags 가 아니다."""
    result = await _fetch(lambda request: httpx.Response(200, json=WANTED_DETAILS))
    payload = result.payload
    assert payload is not None

    assert "식대지원" not in payload.skill_tags
    assert "연봉상위11~20%" not in payload.skill_tags


async def test_empty_skill_tags_is_allowed() -> None:
    """실제로 skill_tags 가 빈 공고가 많다. 실패가 아니다."""
    body = {"application": None, "job": {**WANTED_DETAILS["job"], "skill_tags": []}}

    result = await _fetch(lambda request: httpx.Response(200, json=body))
    payload = result.payload
    assert payload is not None

    assert payload.skill_tags == []
    assert result.status is JdParseStatus.SUCCEEDED


async def test_requirement_categories_and_order() -> None:
    """주요업무 -> 자격요건 -> 우대사항 순으로 display_order 가 1부터 매겨진다."""
    result = await _fetch(lambda request: httpx.Response(200, json=WANTED_DETAILS))
    payload = result.payload
    assert payload is not None

    assert [(item.category, item.text) for item in payload.requirements] == [
        (JdCategory.RESPONSIBILITY, "API 설계"),
        (JdCategory.RESPONSIBILITY, "성능 개선"),
        (JdCategory.REQUIRED, "Python 3년"),
        (JdCategory.REQUIRED, "RDB 경험"),
        (JdCategory.PREFERRED, "대용량 트래픽 경험"),
        (JdCategory.PREFERRED, "Kubernetes"),
    ]
    assert [item.display_order for item in payload.requirements] == [1, 2, 3, 4, 5, 6]


async def test_requirement_limit_is_applied() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=WANTED_DETAILS))
    ) as client:
        result = await WantedAdapter(client=client, requirement_limit=3).fetch(
            "https://www.wanted.co.kr/wd/999"
        )

    payload = result.payload
    assert payload is not None
    assert len(payload.requirements) == 3


# ── 실패 ───────────────────────────────────────────────


async def test_missing_posting_is_not_a_job_posting() -> None:
    """404 는 통신 실패가 아니라 삭제·비공개된 공고다."""
    result = await _fetch(lambda request: httpx.Response(404, json=JOB_NOT_FOUND_BODY))

    assert result.status is JdParseStatus.FAILED
    assert result.error_code == JD_ERROR_NOT_A_JOB_POSTING
    assert result.adapter == "wanted"


@pytest.mark.parametrize("status_code", [400, 403, 500, 503])
async def test_http_error_is_fetch_failed(status_code: int) -> None:
    result = await _fetch(lambda request: httpx.Response(status_code))

    assert result.status is JdParseStatus.FAILED
    assert result.error_code == JD_ERROR_FETCH_FAILED
    # 실패해도 어떤 어댑터를 썼는지 남아야 한다.
    assert result.adapter == "wanted"


async def test_timeout_is_fetch_failed() -> None:
    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timeout", request=request)

    result = await _fetch(timeout)

    assert result.error_code == JD_ERROR_FETCH_FAILED


async def test_non_json_body_is_fetch_failed() -> None:
    result = await _fetch(lambda request: httpx.Response(200, text="<html>not json</html>"))

    assert result.error_code == JD_ERROR_FETCH_FAILED


async def test_empty_payload_is_not_a_job_posting() -> None:
    result = await _fetch(lambda request: httpx.Response(200, json={"application": None}))

    assert result.error_code == JD_ERROR_NOT_A_JOB_POSTING


async def test_missing_requirements_is_partial() -> None:
    """공고는 받았지만 요구사항이 비면 부분 성공이다."""
    body = {
        "application": None,
        "job": {
            "id": 999,
            "detail": {"position": "백엔드 개발자"},
            "company": {"name": "데본"},
        },
    }

    result = await _fetch(lambda request: httpx.Response(200, json=body))

    assert result.status is JdParseStatus.PARTIAL
    assert result.succeeded is True


# ── resolver ───────────────────────────────────────────


def test_resolver_picks_wanted() -> None:
    assert resolve_adapter("https://www.wanted.co.kr/wd/1").name == "wanted"


@pytest.mark.parametrize(
    "url",
    ["https://www.saramin.co.kr/x", "https://www.jobkorea.co.kr/y", "https://example.com"],
)
def test_resolver_falls_back_to_generic(url: str) -> None:
    assert resolve_adapter(url).name == "generic"
    assert normalize_posting_url(url) is None


async def test_unsupported_site_is_blocked() -> None:
    """Sprint 1 은 미지원 사이트를 차단한다. 공고 없이 진행으로 유도하지 않는다."""
    result = await fetch_job_posting("https://www.saramin.co.kr/zf_user/jobs/view?id=1")

    assert result.status is JdParseStatus.FAILED
    assert result.error_code == JD_ERROR_UNSUPPORTED_SITE
    assert result.adapter == "generic"
    assert result.payload is None


async def test_generic_adapter_never_normalizes() -> None:
    adapter = GenericAdapter()

    assert adapter.supports("anything") is True
    assert adapter.normalize_url("anything") is None
