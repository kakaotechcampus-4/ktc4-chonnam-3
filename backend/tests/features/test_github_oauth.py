import httpx
import pytest

from app.core.errors import AppError
from app.features.auth.oauth import GitHubOAuth
from tests.features.test_auth_security import settings


@pytest.mark.parametrize(
    "unexpected",
    [{"expires_in": 3600}, {"refresh_token": "refresh-secret"}, {"refresh_token_expires_in": 1000}],
)
async def test_expiring_github_token_is_rejected(unexpected):
    def response(request):
        if request.url.path == "/user":
            return httpx.Response(200, json={"id": 1, "login": "test"})
        return httpx.Response(
            200, json={"access_token": "secret", "scope": "read:user", **unexpected}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as client:
        with pytest.raises(AppError, match="provider_unavailable"):
            await GitHubOAuth(settings(), client).exchange("code", "verifier")


@pytest.mark.parametrize(
    "payload,status,reason",
    [
        ({"error": "bad_verification_code"}, 200, "invalid_code"),
        ({}, 503, "provider_unavailable"),
        ({"access_token": "secret", "scope": "repo"}, 200, "provider_unavailable"),
        ([], 200, "provider_unavailable"),
    ],
)
async def test_github_provider_errors_are_safe(payload, status, reason):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(status, json=payload))
    ) as client:
        with pytest.raises(AppError, match=reason):
            await GitHubOAuth(settings(), client).exchange("code", "verifier")
