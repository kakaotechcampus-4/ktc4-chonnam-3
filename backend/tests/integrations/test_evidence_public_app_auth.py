"""공개 조회의 앱 인증만 명시하고 주입 client의 비밀·쿠키·redirect를 차단한다."""

import base64

import httpx
import pytest
from pydantic import SecretStr

from app.integrations.github.evidence import EvidenceReader, EvidenceReadError


def reader(http, credentials=("fixture-app-id", SecretStr("fixture-app-secret"))):
    return EvidenceReader(
        http,
        "owner/sample",
        max_requests=4,
        max_response_bytes=4096,
        max_total_bytes=8192,
        timeout_seconds=1,
        public_app_auth=credentials,
    )


async def test_explicit_public_basic_ignores_inherited_auth_cookies_and_cookie_response():
    requests = []
    expected = "Basic " + base64.b64encode(b"fixture-app-id:fixture-app-secret").decode()

    async def provider(request):
        requests.append(request)
        assert request.url.host == "api.github.com"
        assert request.headers["Authorization"] == expected
        assert "cookie" not in request.headers
        assert "fixture-app-secret" not in str(request.url)
        return httpx.Response(200, json={"private": False}, headers={"Set-Cookie": "hidden=value"})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(provider),
        auth=("inherited-id", "inherited-secret"),
        cookies={"inherited": "private-cookie"},
        follow_redirects=True,
    ) as http:
        source = reader(http)
        await source.get("")
        await source.get("/git/trees/" + "a" * 40)
    assert len(requests) == 2


async def test_explicit_user_token_is_not_overridden_by_public_app_auth():
    seen = []

    async def provider(request):
        seen.append(request.headers.get("Authorization"))
        return httpx.Response(200, json={"private": False})

    async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as http:
        source = reader(http)
        await source.get("", token=SecretStr("explicit-user-token"))
        await source.get("/git/trees/" + "a" * 40)
    assert seen[0] == "Bearer explicit-user-token"
    assert seen[1] == "Basic " + base64.b64encode(b"fixture-app-id:fixture-app-secret").decode()


@pytest.mark.parametrize(
    "credentials",
    [
        ("", SecretStr("fixture-secret")),
        ("invalid:id", SecretStr("fixture-secret")),
        ("invalid\n", SecretStr("fixture-secret")),
        ("valid-id", SecretStr("")),
        ("valid-id", SecretStr("invalid\nsecret")),
        ("valid-id", "unwrapped-secret"),
    ],
)
async def test_invalid_app_credentials_fail_without_echoing_secrets(credentials):
    async with httpx.AsyncClient() as http:
        with pytest.raises(EvidenceReadError) as caught:
            reader(http, credentials)
    assert caught.value.code == "github_credentials_invalid"
    assert str(caught.value) == "github_credentials_invalid"


@pytest.mark.parametrize("outcome", ["redirect", "forbidden", "transport"])
async def test_app_credentials_never_follow_redirects_or_enter_errors(outcome):
    seen = []

    async def provider(request):
        seen.append(request)
        assert request.url.host == "api.github.com"
        if outcome == "transport":
            raise httpx.ConnectError("fixture-app-secret", request=request)
        return httpx.Response(
            302 if outcome == "redirect" else 403,
            text="fixture-app-secret",
            headers={"Location": "https://untrusted.example.test/stolen"},
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(provider), follow_redirects=True
    ) as http:
        with pytest.raises(EvidenceReadError) as caught:
            await reader(http).get("")
    expected = {
        "redirect": "github_http_302",
        "forbidden": "github_http_403",
        "transport": "github_transport_error",
    }
    assert str(caught.value) == expected[outcome]
    assert len(seen) == 1
