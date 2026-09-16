import httpx
import pytest

from app.core.errors import AppError
from app.integrations.github import client as github


@pytest.mark.parametrize(
    "path", ["https://evil.test/user", "//evil.test/user", "/user?token=secret", "/user#fragment"]
)
async def test_github_client_rejects_non_api_paths_before_sending_token(path):
    def unexpected(request):
        pytest.fail("Unsafe paths must not send any HTTP request")

    assert hasattr(github, "GitHubClient"), "GitHub calls need a fixed-origin HTTP client"
    async with httpx.AsyncClient(transport=httpx.MockTransport(unexpected)) as http:
        with pytest.raises(ValueError):
            await github.GitHubClient(http).get(path, "private-token")


@pytest.mark.parametrize(
    "status,reason",
    [
        (401, "token_invalid"),
        (403, "provider_unavailable"),
        (429, "provider_unavailable"),
        (503, "provider_unavailable"),
        (302, "provider_unavailable"),
    ],
)
async def test_provider_failures_do_not_leak_credentials_or_follow_redirects(status, reason):
    def response(request):
        assert request.url.host == "api.github.com"
        assert request.headers["authorization"] == "Bearer private-token"
        return httpx.Response(
            status, json={"message": "private-token"}, headers={"Location": "https://evil.test"}
        )

    assert hasattr(github, "GitHubClient")
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(response), follow_redirects=True
    ) as http:
        with pytest.raises(AppError, match=reason) as error:
            await github.GitHubClient(http).get("/user", "private-token")
        assert "private-token" not in str(error.value)


async def test_github_client_returns_json_and_uses_query_parameters():
    def response(request):
        assert request.url.params["page"] == "2"
        assert request.headers["authorization"] == "Bearer private-token"
        return httpx.Response(200, json=[{"id": 123}])

    assert hasattr(github, "GitHubClient")
    async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as http:
        assert await github.GitHubClient(http).get(
            "/user/repos", "private-token", {"page": "2"}
        ) == [{"id": 123}]


@pytest.mark.parametrize("body", [b"not-json", b"null", b"42", b'"string"'])
async def test_github_client_rejects_malformed_api_payloads(body):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=body))
    ) as http:
        with pytest.raises(AppError, match="provider_unavailable"):
            await github.GitHubClient(http).get("/user", "private-token")


async def test_github_client_sanitizes_network_errors():
    def failure(request):
        raise httpx.ReadTimeout("private-token")

    async with httpx.AsyncClient(transport=httpx.MockTransport(failure)) as http:
        with pytest.raises(AppError, match="provider_unavailable") as error:
            await github.GitHubClient(http).get("/user", "private-token")
        assert "private-token" not in str(error.value)
