import httpx
import pytest

from app.integrations.jd.base import PostingFetchError
from app.integrations.jd.wanted import WantedAdapter

WANTED_URL = "https://www.wanted.co.kr/wd/123456"


def _raise_connect_error(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("connection failed", request=request)


@pytest.mark.parametrize(
    "handler",
    [
        pytest.param(
            lambda request: httpx.Response(404),
            id="http-404",
        ),
        pytest.param(
            _raise_connect_error,
            id="network-error",
        ),
        pytest.param(
            lambda request: httpx.Response(
                200,
                json={
                    "job": {
                        "position": None,
                        "detail": {},
                        "company": {},
                        "skill_tags": [],
                    }
                },
            ),
            id="empty-content",
        ),
        pytest.param(
            lambda request: httpx.Response(
                200,
                content=b"not json",
                headers={"content-type": "text/plain"},
            ),
            id="non-json-response",
        ),
    ],
)
async def test_fetch_failures_use_canonical_error_code(handler):
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = WantedAdapter(client=client)

        with pytest.raises(PostingFetchError) as exc_info:
            await adapter.fetch(WANTED_URL)

    assert exc_info.value.code == "jd_fetch_failed"
