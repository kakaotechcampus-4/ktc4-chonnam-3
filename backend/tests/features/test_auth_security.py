import asyncio
import base64
from uuid import uuid4

import httpx
import pytest


def test_cipher_encrypts_with_unique_nonce_and_rejects_tampering():
    from app.core import crypto

    cipher = crypto.TokenCipher(base64.b64encode(b"k" * 32).decode())
    one = cipher.encrypt("github-secret")
    two = cipher.encrypt("github-secret")
    assert one != two
    assert b"github-secret" not in one
    assert cipher.decrypt(one) == "github-secret"
    with pytest.raises(ValueError):
        cipher.decrypt(one[:-1] + bytes([one[-1] ^ 1]))


@pytest.mark.parametrize("key", ["invalid", base64.b64encode(b"short").decode()])
def test_cipher_rejects_invalid_key(key):
    from app.core.crypto import TokenCipher

    with pytest.raises(ValueError):
        TokenCipher(key)


async def test_sessions_expire_slide_and_cannot_be_resurrected(redis):
    from app.features.auth.session_store import SessionStore

    store = SessionStore(redis, 1209600)
    user_id = uuid4()
    sid = await store.create(user_id)
    assert len(sid) >= 43
    assert await redis.get(f"auth:sess:{sid}") == str(user_id).encode()
    await redis.expire(f"auth:sess:{sid}", 30)
    assert await store.get(sid) == user_id
    assert await store.touch(sid)
    assert await redis.ttl(f"auth:sess:{sid}") > 1209500
    await store.delete(sid)
    await asyncio.gather(store.touch(sid), store.delete(sid))
    assert await store.get(sid) is None
    assert not await store.touch(sid)
    await redis.set(f"auth:sess:{sid}", str(user_id), px=1)
    await asyncio.sleep(0.01)
    assert await store.get(sid) is None


async def test_oauth_state_is_browser_bound_single_use_and_purpose_bound(redis):
    from app.core.errors import AppError, Reason
    from app.features.auth.oauth import OAuthStateStore

    store = OAuthStateStore(redis)
    state, verifier = await store.create("login")
    assert len(verifier) >= 43
    assert 0 < await redis.ttl(f"auth:oauth:{state}") <= 600
    with pytest.raises(AppError) as error:
        await store.consume(state, "different-browser", "login")
    assert error.value.reason == Reason.INVALID_STATE
    record = await store.consume(state, state, "login")
    assert record.verifier == verifier
    with pytest.raises(AppError):
        await store.consume(state, state, "login")
    state, _ = await store.create("link", uuid4())
    with pytest.raises(AppError):
        await store.consume(state, state, "login")


async def test_oauth_state_expires(redis):
    from app.core.errors import AppError, Reason
    from app.features.auth.oauth import OAuthStateStore

    store = OAuthStateStore(redis)
    state, _ = await store.create("login")
    await redis.pexpire(f"auth:oauth:{state}", 1)
    await asyncio.sleep(0.01)
    with pytest.raises(AppError) as error:
        await store.consume(state, state, "login")
    assert error.value.reason == Reason.INVALID_STATE


async def test_non_ascii_browser_cookie_is_invalid_state_not_server_error(redis):
    from app.core.errors import AppError, Reason
    from app.features.auth.oauth import OAuthStateStore

    store = OAuthStateStore(redis)
    state, _ = await store.create("login")
    with pytest.raises(AppError) as error:
        await store.consume(state, "\u00e9", "login")
    assert error.value.reason == Reason.INVALID_STATE


async def test_provider_non_ascii_token_is_rejected_before_header_encoding(app_settings):
    from app.core.errors import AppError, Reason
    from app.features.auth.oauth import GitHubOAuth

    payload = {"access_token": "secret\u00e9", "token_type": "bearer", "scope": "read:user"}
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))
    ) as client:
        with pytest.raises(AppError) as error:
            await GitHubOAuth(app_settings, client).exchange_code("code", "verifier", "login")
    assert error.value.reason == Reason.PROVIDER_UNAVAILABLE


@pytest.mark.parametrize("purpose", ["login", "link"])
async def test_oauth_uses_pkce_and_public_callback_and_validates_profile(app_settings, purpose):
    from urllib.parse import parse_qs, urlsplit

    from app.features.auth.oauth import GitHubOAuth

    # RFC 7636 Appendix B interoperability vector.
    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"

    def github(request):
        if request.url.path == "/login/oauth/access_token":
            data = parse_qs(request.content.decode())
            assert data["redirect_uri"] == [app_settings.github_redirect_uri]
            assert data["code_verifier"] == [verifier]
            return httpx.Response(
                200,
                json={
                    "access_token": "private-token",
                    "token_type": "bearer",
                    "scope": "read:user",
                },
            )
        assert request.headers["authorization"] == "Bearer private-token"
        return httpx.Response(
            200,
            json={
                "id": 1234,
                "login": "octocat",
                "name": None,
                "avatar_url": None,
                "public_repos": 2,
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(github)) as client:
        oauth = GitHubOAuth(app_settings, client)
        params = parse_qs(urlsplit(oauth.authorize_url("state", verifier, purpose)).query)
        assert params["redirect_uri"] == [app_settings.github_redirect_uri]
        assert params["code_challenge_method"] == ["S256"]
        assert params["code_challenge"] == ["E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"]
        assert params["scope"] == ["read:user"]
        token = await oauth.exchange_code("code", verifier, purpose)
        profile = await oauth.fetch_profile(token.access_token)
        assert profile.github_user_id == 1234
        assert profile.name == "octocat"


@pytest.mark.parametrize(
    "payload",
    [
        {
            "access_token": "secret",
            "token_type": "bearer",
            "scope": "read:user",
            "refresh_token": "refresh",
        },
        {
            "access_token": "secret",
            "token_type": "bearer",
            "scope": "read:user",
            "expires_in": 3600,
        },
        {"access_token": "secret", "token_type": "mac", "scope": "read:user"},
        {"access_token": "secret"},
        [],
    ],
)
async def test_oauth_rejects_unsupported_token_payloads(app_settings, payload):
    from app.core.errors import AppError, Reason
    from app.features.auth.oauth import GitHubOAuth

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))
    ) as client:
        with pytest.raises(AppError) as error:
            await GitHubOAuth(app_settings, client).exchange_code("code", "verifier", "login")
    assert error.value.reason == Reason.PROVIDER_UNAVAILABLE
    assert "secret" not in str(error.value.to_envelope())


@pytest.mark.parametrize(
    "payload",
    [
        {"id": True, "login": "x"},
        {"id": 0, "login": "x"},
        {"id": "123", "login": "x"},
        {"id": 123, "login": ""},
        [],
    ],
)
async def test_oauth_rejects_malformed_identity(app_settings, payload):
    from app.core.errors import AppError, Reason
    from app.features.auth.oauth import GitHubOAuth

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))
    ) as client:
        with pytest.raises(AppError) as error:
            await GitHubOAuth(app_settings, client).fetch_profile("secret")
    assert error.value.reason == Reason.PROVIDER_UNAVAILABLE


@pytest.mark.parametrize(
    "status,reason",
    [
        (401, "invalid_code"),
        (400, "invalid_code"),
        (403, "provider_unavailable"),
        (429, "provider_unavailable"),
        (500, "provider_unavailable"),
    ],
)
async def test_oauth_maps_provider_failures_without_leaking_body(app_settings, status, reason):
    from app.core.errors import AppError
    from app.features.auth.oauth import GitHubOAuth

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(status, text="provider-secret"))
    ) as client:
        with pytest.raises(AppError) as error:
            await GitHubOAuth(app_settings, client).exchange_code("code", "verifier", "login")
    assert error.value.reason == reason
    assert "provider-secret" not in str(error.value.to_envelope())
