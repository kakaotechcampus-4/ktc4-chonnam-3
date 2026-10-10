"""기본 7일과 다른 TTL이 수집·저장 양쪽의 재사용 판단에 반영되는지 검증한다."""

from copy import deepcopy
from datetime import timedelta

import httpx
import pytest

from app.features.analysis import posting_service
from tests.features.test_postings import NOW, PAYLOAD, URL, _fetch, _requirements
from tests.features.test_postings import posting_sessions as posting_sessions


@pytest.mark.parametrize(
    ("age", "expected_http_count"),
    [(timedelta(days=2), 0), (timedelta(days=2, microseconds=1), 1)],
)
async def test_configured_ttl_reuses_boundary_and_refetches_after_expiry(
    posting_sessions, age, expected_http_count
):
    first = await _fetch(posting_sessions)
    changed = deepcopy(PAYLOAD)
    changed["job"]["detail"]["requirements"] = ["Go 경험"]
    http_count = 0

    def respond(request):
        nonlocal http_count
        http_count += 1
        return httpx.Response(200, json=changed)

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        result = await posting_service.get_or_fetch_posting(
            posting_sessions, URL, client=client, now=NOW + age, reuse_ttl_days=2
        )

    assert http_count == expected_http_count
    if expected_http_count:
        assert result.id != first.id
        assert result.fetched_at == NOW + age
        assert (await _requirements(posting_sessions, result.id))[0].text == "Go 경험"
    else:
        assert result.id == first.id
        assert result.fetched_at == NOW


async def test_complete_rechecks_concurrent_posting_with_prepared_ttl(posting_sessions):
    changed = deepcopy(PAYLOAD)
    changed["job"]["detail"]["requirements"] = ["Go 경험"]
    later = NOW + timedelta(days=3)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=changed))
    ) as client:
        prepared = await posting_service.fetch_posting(
            posting_sessions, URL, client=client, now=later, reuse_ttl_days=2
        )

    # 수집과 저장 사이에 다른 요청이 자료를 확정해도 전달된 2일 기준으로 다시 판단한다.
    previous = await _fetch(posting_sessions)
    result = await posting_service.complete_posting(posting_sessions, prepared)

    assert result.id != previous.id
    assert result.fetched_at == later
    assert (await _requirements(posting_sessions, result.id))[0].text == "Go 경험"
    assert (await _requirements(posting_sessions, previous.id))[0].text == "Python 경험"
