"""Wanted 공고 수집과 어댑터 선택.

spec/backend/features/analysis-run.md / task-09

⚠ 원티드 응답의 정확한 중첩 구조는 확인하지 못했다. 아래 fixture 는 확정본에 적힌
  필드 이름으로 만든 것이라 파서 로직을 검증하지 실제 API 계약을 증명하지 않는다.
"""

from collections.abc import Callable

import httpx
import pytest

from app.integrations.jd.base import (
    JD_ERROR_FETCH_FAILED,
    JD_ERROR_NOT_A_JOB_POSTING,
    JD_ERROR_UNSUPPORTED_SITE,
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

WANTED_DETAILS = {
    "data": {
        "job": {
            "position": "백엔드 개발자",
            "company": {"name": "데본"},
            "detail": {
                "intro": "회사 소개",
                "main_tasks": "- API 설계\n- 성능 개선",
                "requirements": "- Python 3년\n- RDB 경험",
                "preferred_points": "• 대용량 트래픽 경험\n1) Kubernetes",
                "benefits": "식대 지원",
            },
            "skill_tags": [{"title": "Python"}, {"title": "FastAPI"}, "PostgreSQL"],
            "industry_name": "IT",
        }
    }
}


async def _fetch(
    handler: Callable[[httpx.Request], httpx.Response],
    url: str = "https://www.wanted.co.kr/wd/999",
) -> object:
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        return await WantedAdapter(client=client).fetch(url)


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
    assert payload.skill_tags == ["Python", "FastAPI", "PostgreSQL"]


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


@pytest.mark.parametrize("status_code", [400, 404, 500, 503])
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
    result = await _fetch(lambda request: httpx.Response(200, json={"data": {}}))

    assert result.error_code == JD_ERROR_NOT_A_JOB_POSTING


async def test_missing_requirements_is_partial() -> None:
    """공고는 받았지만 요구사항이 비면 부분 성공이다."""
    body = {"data": {"job": {"position": "백엔드 개발자", "company": {"name": "데본"}}}}

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
