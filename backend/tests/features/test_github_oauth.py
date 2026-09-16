import base64
import hashlib
import traceback
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from pydantic import SecretStr

from app.core.errors import AppError
from app.features.auth import oauth
from app.features.auth.oauth import GitHubOAuth
from tests.features.test_auth_security import settings


def token_payload(**updates):
    return {
        "access_token": "new-access-secret",
        "refresh_token": "new-refresh-secret",
        "token_type": "bearer",
        "scope": "read:user",
        "expires_in": 28800,
        "refresh_token_expires_in": 15897600,
        **updates,
    }


def test_authorization_uses_read_user_scope_and_s256_pkce():
    cfg = settings()
    verifier = "test-verifier"
    url = GitHubOAuth(cfg, None).authorization_url("test-state", verifier)
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    assert (parsed.scheme, parsed.netloc, parsed.path) == (
        "https",
        "github.com",
        "/login/oauth/authorize",
    )
    assert query == {
        "client_id": [cfg.github_client_id],
        "redirect_uri": [cfg.github_redirect_uri],
        "scope": ["read:user"],
        "state": ["test-state"],
        "code_challenge": [
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .rstrip(b"=")
            .decode()
        ],
        "code_challenge_method": ["S256"],
    }


@pytest.mark.parametrize("operation", ["exchange", "refresh"])
@pytest.mark.parametrize("scope", ["read:user", "read:user,user:email", "repo read:user"])
async def test_expiring_tokens_use_request_start_and_hide_secrets(monkeypatch, operation, scope):
    class Clock(datetime):
        current = datetime(2026, 9, 17, 0, 0, tzinfo=UTC)

        @classmethod
        def now(cls, tz=None):
            return cls.current

    monkeypatch.setattr(oauth, "datetime", Clock, raising=False)
    requests = []

    def response(request):
        requests.append(request)
        if request.url.path == "/user":
            assert request.headers["Authorization"] == "Bearer new-access-secret"
            assert request.headers["X-GitHub-Api-Version"] == "2022-11-28"
            return httpx.Response(200, json={"id": 1, "login": "test"})
        Clock.current = datetime(2026, 9, 17, 0, 0, 30, tzinfo=UTC)
        return httpx.Response(200, json=token_payload(scope=scope))

    cfg = settings()
    async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as client:
        provider = GitHubOAuth(cfg, client)
        if operation == "exchange":
            identity = await provider.exchange("code", "verifier")
            assert identity.profile.id == 1
            assert identity.profile.login == "test"
            assert "new-access-secret" not in repr(identity)
            assert "new-refresh-secret" not in repr(identity)
            tokens = identity.tokens
            assert len(requests) == 2
        else:
            tokens = await provider.refresh("old-refresh-secret")
            assert len(requests) == 1

    assert tokens.access_token == "new-access-secret"
    assert tokens.refresh_token == "new-refresh-secret"
    assert tokens.scope == scope
    assert tokens.expires_at == datetime(2026, 9, 17, 8, 0, tzinfo=UTC)
    assert tokens.refresh_expires_at == datetime(2027, 3, 20, 0, 0, tzinfo=UTC)
    assert "new-access-secret" not in repr(tokens)
    assert "new-refresh-secret" not in repr(tokens)
    assert str(requests[0].url) == "https://github.com/login/oauth/access_token"
    assert requests[0].headers["Accept"] == "application/json"
    data = parse_qs(requests[0].content.decode())
    expected = {
        "client_id": [cfg.github_client_id],
        "client_secret": [cfg.github_client_secret.get_secret_value()],
    }
    if operation == "exchange":
        expected.update(
            redirect_uri=[cfg.github_redirect_uri], code=["code"], code_verifier=["verifier"]
        )
    else:
        expected.update(grant_type=["refresh_token"], refresh_token=["old-refresh-secret"])
    assert data == expected


@pytest.mark.parametrize("operation", ["exchange", "refresh"])
@pytest.mark.parametrize(
    "missing",
    [
        "access_token",
        "refresh_token",
        "token_type",
        "scope",
        "expires_in",
        "refresh_token_expires_in",
    ],
)
async def test_incomplete_expiring_tokens_are_rejected(operation, missing):
    payload = token_payload()
    del payload[missing]
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    ) as client:
        with pytest.raises(AppError, match="provider_unavailable") as caught:
            provider = GitHubOAuth(settings(), client)
            if operation == "exchange":
                await provider.exchange("code", "verifier")
            else:
                await provider.refresh("old-refresh-secret")
    assert caught.value.status == 503


@pytest.mark.parametrize("operation", ["exchange", "refresh"])
@pytest.mark.parametrize(
    "updates",
    [
        {"access_token": ""},
        {"access_token": " "},
        {"access_token": 123},
        {"refresh_token": ""},
        {"refresh_token": " "},
        {"refresh_token": False},
        {"token_type": "basic"},
        {"token_type": None},
        {"scope": "repo"},
        {"scope": ["read:user"]},
        {"expires_in": 0},
        {"expires_in": -1},
        {"expires_in": True},
        {"expires_in": "28800"},
        {"expires_in": 28800.0},
        {"expires_in": 10**100},
        {"refresh_token_expires_in": 0},
        {"refresh_token_expires_in": -1},
        {"refresh_token_expires_in": True},
        {"refresh_token_expires_in": "15897600"},
        {"refresh_token_expires_in": 15897600.0},
        {"refresh_token_expires_in": 10**100},
        {"error": "incorrect_client_credentials"},
    ],
)
async def test_malformed_expiring_tokens_are_rejected(operation, updates):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=token_payload(**updates))
        )
    ) as client:
        with pytest.raises(AppError, match="provider_unavailable") as caught:
            provider = GitHubOAuth(settings(), client)
            if operation == "exchange":
                await provider.exchange("code", "verifier")
            else:
                await provider.refresh("old-refresh-secret")
    assert caught.value.status == 503


@pytest.mark.parametrize(
    "operation,payload,status,reason,expected_status",
    [
        ("exchange", {"error": "bad_verification_code"}, 200, "invalid_code", 400),
        ("exchange", {"error": "bad_verification_code"}, 403, "provider_unavailable", 503),
        ("exchange", {"error": "bad_verification_code"}, 503, "provider_unavailable", 503),
        ("exchange", [], 200, "provider_unavailable", 503),
        ("refresh", {"error": "bad_refresh_token"}, 200, "token_invalid", 401),
        ("refresh", {"error": "bad_refresh_token"}, 400, "token_invalid", 401),
        ("refresh", {"error": "bad_refresh_token"}, 403, "provider_unavailable", 503),
        ("refresh", {"error": "bad_refresh_token"}, 503, "provider_unavailable", 503),
        ("refresh", {"error": "bad_refresh_token"}, 429, "provider_unavailable", 503),
        ("refresh", {"error": "incorrect_client_credentials"}, 200, "provider_unavailable", 503),
        ("refresh", {"error": "bad_verification_code"}, 200, "provider_unavailable", 503),
        ("refresh", {}, 401, "provider_unavailable", 503),
        ("refresh", [], 200, "provider_unavailable", 503),
    ],
)
async def test_github_provider_errors_are_safe(operation, payload, status, reason, expected_status):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(status, json=payload))
    ) as client:
        with pytest.raises(AppError, match=reason) as caught:
            provider = GitHubOAuth(settings(), client)
            if operation == "exchange":
                await provider.exchange("code", "verifier")
            else:
                await provider.refresh("old-refresh-secret")
    assert caught.value.status == expected_status


@pytest.mark.parametrize("operation", ["exchange", "refresh", "profile"])
@pytest.mark.parametrize("failure", ["network", "non_json"])
async def test_provider_failures_do_not_expose_secrets(operation, failure):
    access_token = "new-access-secret"
    refresh_token = "old-refresh-secret"

    def response(request):
        if failure == "network":
            raise httpx.ConnectError("new-access-secret old-refresh-secret", request=request)
        return httpx.Response(200, text="new-access-secret old-refresh-secret")

    async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as client:
        with pytest.raises(AppError, match="provider_unavailable") as caught:
            provider = GitHubOAuth(settings(), client)
            if operation == "exchange":
                await provider.exchange("code", "verifier")
            elif operation == "refresh":
                await provider.refresh(refresh_token)
            else:
                await provider.profile(access_token)
    rendered = "".join(traceback.format_exception(caught.value))
    assert "new-access-secret" not in rendered
    assert "old-refresh-secret" not in rendered
    assert caught.value.status == 503


@pytest.mark.parametrize("operation", ["exchange", "refresh"])
async def test_missing_oauth_configuration_does_not_contact_github(operation):
    def response(request):
        pytest.fail("Missing client credentials must not be sent to GitHub")

    cfg = settings().model_copy(
        update={"github_client_id": "", "github_client_secret": SecretStr("")}
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as client:
        with pytest.raises(AppError, match="provider_unavailable"):
            provider = GitHubOAuth(cfg, client)
            if operation == "exchange":
                await provider.exchange("code", "verifier")
            else:
                await provider.refresh("old-refresh-secret")


@pytest.mark.parametrize("code", ["", "x" * 2049])
async def test_invalid_code_does_not_contact_github(code):
    def response(request):
        pytest.fail("Invalid code must not be sent to GitHub")

    async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as client:
        with pytest.raises(AppError, match="invalid_code") as caught:
            await GitHubOAuth(settings(), client).exchange(code, "verifier")
    assert caught.value.status == 400


async def test_profile_revalidates_the_current_github_user():
    def response(request):
        assert str(request.url) == "https://api.github.com/user"
        assert request.headers["Authorization"] == "Bearer access-secret"
        return httpx.Response(200, json={"id": 123, "login": "current-user"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as client:
        profile = await GitHubOAuth(settings(), client).profile("access-secret")
    assert profile.id == 123
    assert profile.login == "current-user"


@pytest.mark.parametrize("operation", ["exchange", "profile"])
@pytest.mark.parametrize("status,payload", [(401, {}), (403, {}), (429, {}), (503, {}), (200, [])])
async def test_profile_failures_preserve_callback_error_contract(operation, status, payload):
    def response(request):
        if request.url.path != "/user":
            return httpx.Response(200, json=token_payload())
        return httpx.Response(status, json=payload)

    reason = "token_invalid" if operation == "profile" and status == 401 else "provider_unavailable"
    async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as client:
        with pytest.raises(AppError, match=reason) as caught:
            provider = GitHubOAuth(settings(), client)
            if operation == "exchange":
                await provider.exchange("code", "verifier")
            else:
                await provider.profile("access-secret")
    assert caught.value.status == (401 if reason == "token_invalid" else 503)


@pytest.mark.parametrize("operation", ["exchange", "refresh", "profile"])
@pytest.mark.parametrize("status", [307, 308])
async def test_oauth_requests_never_follow_redirects_with_secrets(operation, status):
    hosts = []

    def response(request):
        hosts.append(request.url.host)
        if request.url.host == "evil.test":
            return httpx.Response(200, json={**token_payload(), "id": 1, "login": "test"})
        return httpx.Response(status, headers={"Location": "https://evil.test/capture"})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(response), follow_redirects=True
    ) as client:
        with pytest.raises(AppError, match="provider_unavailable"):
            provider = GitHubOAuth(settings(), client)
            if operation == "exchange":
                await provider.exchange("code", "verifier")
            elif operation == "refresh":
                await provider.refresh("old-refresh-secret")
            else:
                await provider.profile("access-secret")
    assert hosts == ["api.github.com" if operation == "profile" else "github.com"]
