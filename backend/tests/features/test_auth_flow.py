import asyncio
import base64
import hashlib
import os
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import create_async_engine

from app import main
from tests.features.test_auth_security import settings


def test_app_factory_exists():
    assert hasattr(main, "create_app"), "Auth routes need an injectable app factory"


@pytest.fixture
async def runtime():
    db_url = os.environ.get("TEST_DATABASE_URL")
    redis_url = os.environ.get("TEST_REDIS_URL")
    if not db_url or not redis_url:
        pytest.skip(
            "Set isolated TEST_DATABASE_URL and TEST_REDIS_URL for PostgreSQL/Redis integration"
        )
    assert "test" in urlsplit(db_url).path.lower(), "Use an explicitly named test database"
    assert urlsplit(redis_url).path not in {"", "/", "/0"}, "Use an isolated Redis database"
    from app.db.base import Base

    cfg = settings().model_copy(update={"database_url": db_url, "redis_url": redis_url})
    engine = create_async_engine(db_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    redis = Redis.from_url(redis_url, decode_responses=True)
    await redis.flushdb()

    def github(request):
        if request.url.path == "/login/oauth/access_token":
            assert b"code_verifier=" in request.content
            return httpx.Response(200, json=github_tokens())
        return httpx.Response(
            200,
            json={
                "id": 12345,
                "login": "octo",
                "name": "Octo",
                "avatar_url": "https://avatars.githubusercontent.com/u/12345",
            },
        )

    transport = httpx.MockTransport(github)
    app = main.create_app(cfg, github_transport=transport)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url=cfg.frontend_origin
        ) as client:
            yield app, client, redis
    await redis.flushdb()
    await redis.aclose()
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
    await engine.dispose()


def github_tokens(access_token="gho_private", refresh_token="ghr_private"):
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "scope": "read:user",
        "expires_in": 28800,
        "refresh_token_expires_in": 15897600,
    }


async def login(client):
    response = await client.get("/api/auth/github/login")
    assert response.status_code == 302
    query = parse_qs(urlsplit(response.headers["location"]).query)
    assert query["scope"] == ["read:user"]
    assert query["code_challenge_method"] == ["S256"]
    callback = await client.get(
        "/api/auth/github/callback", params={"state": query["state"][0], "code": "one-use-code"}
    )
    assert callback.status_code == 302
    assert callback.headers["location"].endswith("/home")
    assert "gho_private" not in callback.text + str(callback.headers)
    return callback


async def test_login_me_rotate_replay_and_logout(runtime):
    app, client, redis = runtime
    response = await login(client)
    cookies = response.headers.get_list("set-cookie")
    assert all("HttpOnly" in cookie and "SameSite=lax" in cookie for cookie in cookies)
    assert any("refreshToken=" in cookie and "Path=/api/auth" in cookie for cookie in cookies)
    me = await client.get("/api/me")
    assert me.json() == {
        "name": "Octo",
        "avatarUrl": "https://avatars.githubusercontent.com/u/12345",
        "githubLinked": True,
    }
    old_refresh = client.cookies.get("refreshToken")
    assert (await client.post("/api/auth/refresh")).status_code == 403
    origin = {"Origin": app.state.settings.frontend_origin}
    assert (await client.post("/api/auth/refresh", headers=origin)).status_code == 204
    rotated = client.cookies.get("refreshToken")
    assert rotated != old_refresh
    replay = await client.post(
        "/api/auth/refresh", headers={**origin, "Cookie": f"refreshToken={old_refresh}"}
    )
    assert replay.status_code == 401
    invalidated = await client.post(
        "/api/auth/refresh", headers={**origin, "Cookie": f"refreshToken={rotated}"}
    )
    assert invalidated.status_code == 401
    await login(client)
    fresh = client.cookies.get("refreshToken")
    await client.post(
        "/api/auth/refresh", headers={**origin, "Cookie": f"refreshToken={old_refresh}"}
    )
    assert (
        await client.post(
            "/api/auth/refresh", headers={**origin, "Cookie": f"refreshToken={fresh}"}
        )
    ).status_code == 204
    logout = await client.post("/api/auth/logout", headers=origin)
    assert logout.status_code == 204 and not logout.content
    assert (await client.get("/api/me")).status_code == 401
    assert (await client.post("/api/auth/logout", headers=origin)).status_code == 204


async def test_state_browser_binding_single_use_and_denial(runtime):
    app, client, redis = runtime
    start = await client.get("/api/auth/github/login")
    query = parse_qs(urlsplit(start.headers["location"]).query)
    state = query["state"][0]
    stored = await redis.hgetall(f"auth:oauth:{state}")
    assert (
        query["code_challenge"][0]
        == base64.urlsafe_b64encode(hashlib.sha256(stored["verifier"].encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    denied = await client.get(
        "/api/auth/github/callback", params={"state": state, "error": "access_denied"}
    )
    assert denied.headers["location"].endswith("/login?error=denied")
    replay = await client.get("/api/auth/github/callback", params={"state": state, "code": "again"})
    assert replay.headers["location"].endswith("/login?error=invalid_state")
    start = await client.get("/api/auth/github/login")
    state = parse_qs(urlsplit(start.headers["location"]).query)["state"][0]
    client.cookies.delete("oauthState")
    wrong_browser = await client.get(
        "/api/auth/github/callback", params={"state": state, "code": "code"}
    )
    assert wrong_browser.headers["location"].endswith("/login?error=invalid_state")


async def test_concurrent_signup_and_encrypted_storage(runtime):
    from app.db.models.user import GitHubAccount, User

    app, client, redis = runtime

    async def browser():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url=app.state.settings.frontend_origin
        ) as other:
            await login(other)

    await asyncio.gather(*(browser() for _ in range(5)))
    async with app.state.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(User)) == 1
        assert await session.scalar(select(func.count()).select_from(GitHubAccount)) == 1
        account = await session.scalar(select(GitHubAccount))
        assert b"gho_private" not in account.access_token_encrypted
        assert app.state.cipher.decrypt(account.access_token_encrypted) == "gho_private"
        assert b"ghr_private" not in account.refresh_token_encrypted
        assert app.state.cipher.decrypt(account.refresh_token_encrypted) == "ghr_private"
        assert account.token_expires_at < account.refresh_token_expires_at


@pytest.mark.parametrize("status", ["suspended", "withdrawn"])
async def test_blocked_accounts_cannot_login_refresh_or_read_me(runtime, status):
    from app.db.models.user import User

    app, client, redis = runtime
    await login(client)
    async with app.state.sessions() as session:
        user = await session.scalar(select(User))
        user.status = status
        await session.commit()
    reason = f"account_{status}"
    assert (await client.get("/api/me")).json()["error"]["reason"] == reason
    response = await client.post(
        "/api/auth/refresh", headers={"Origin": app.state.settings.frontend_origin}
    )
    assert response.status_code == 403 and response.json()["error"]["reason"] == reason
    start = await client.get("/api/auth/github/login")
    state = parse_qs(urlsplit(start.headers["location"]).query)["state"][0]
    callback = await client.get(
        "/api/auth/github/callback", params={"state": state, "code": "code"}
    )
    assert callback.headers["location"].endswith(f"/login?error={reason}")


async def test_redis_outage_does_not_affect_existing_session(runtime):
    from app.features.auth.session_store import OAuthStateStore

    app, client, redis = runtime
    await login(client)
    broken = Redis.from_url(
        "redis://127.0.0.1:1/15", socket_connect_timeout=0.1, socket_timeout=0.1
    )
    app.state.oauth_states = OAuthStateStore(broken)
    try:
        assert (await client.get("/api/me")).status_code == 200
        for route in ("refresh", "logout"):
            response = await client.post(
                f"/api/auth/{route}", headers={"Origin": app.state.settings.frontend_origin}
            )
            assert response.status_code == 204
        client.cookies.clear()
        assert (
            await client.post(
                "/api/auth/logout", headers={"Origin": app.state.settings.frontend_origin}
            )
        ).status_code == 204
        assert (await client.get("/api/auth/github/login")).status_code == 503
    finally:
        await broken.aclose()


@pytest.mark.parametrize("origin", [None, "http://localhost:5173/", "https://evil.test", "null"])
async def test_logout_requires_exact_origin(runtime, origin):
    app, client, redis = runtime
    response = await client.post("/api/auth/logout", headers={"Origin": origin} if origin else {})
    assert response.status_code == 403
    assert response.json()["error"]["reason"] == "invalid_origin"


async def test_revoked_github_token_changes_me_linked_flag(runtime):
    from app.db.models.user import GitHubAccount

    app, client, redis = runtime
    await login(client)
    async with app.state.sessions() as session:
        account = await session.scalar(select(GitHubAccount))
        account.token_status = "revoked"
        await session.commit()
    assert (await client.get("/api/me")).json()["githubLinked"] is False


async def test_missing_oauth_configuration_returns_503_without_redirect(runtime):
    app, client, redis = runtime
    app.state.settings = app.state.settings.model_copy(update={"github_client_id": ""})
    response = await client.get("/api/auth/github/login")
    assert response.status_code == 503
    assert response.json()["error"]["reason"] == "service_unavailable"
    assert "location" not in response.headers


async def test_state_wrong_binding_and_expiration(runtime):
    app, client, redis = runtime
    start = await client.get("/api/auth/github/login")
    state = parse_qs(urlsplit(start.headers["location"]).query)["state"][0]
    assert 590 <= await redis.ttl(f"auth:oauth:{state}") <= 600
    wrong = await client.get(
        "/api/auth/github/callback",
        params={"state": state, "code": "code"},
        headers={"Cookie": "oauthState=wrong-browser"},
    )
    assert wrong.headers["location"].endswith("/login?error=invalid_state")
    assert await redis.exists(f"auth:oauth:{state}")
    start = await client.get("/api/auth/github/login")
    state = parse_qs(urlsplit(start.headers["location"]).query)["state"][0]
    await redis.expire(f"auth:oauth:{state}", 0)
    expired = await client.get("/api/auth/github/callback", params={"state": state, "code": "code"})
    assert expired.headers["location"].endswith("/login?error=invalid_state")


async def test_missing_access_refresh_and_access_survives_logout(runtime):
    app, client, redis = runtime
    await login(client)
    access = client.cookies.get("accessToken")
    client.cookies.delete("accessToken")
    assert (await client.get("/api/me")).json()["error"]["reason"] == "unauthenticated"
    origin = {"Origin": app.state.settings.frontend_origin}
    assert (await client.post("/api/auth/refresh", headers=origin)).status_code == 204
    assert (await client.get("/api/me")).status_code == 200
    await client.post("/api/auth/logout", headers=origin)
    assert (
        await client.get("/api/me", headers={"Cookie": f"accessToken={access}"})
    ).status_code == 200


async def test_relogin_updates_profile_and_falls_back_to_login(runtime):
    app, client, redis = runtime
    await login(client)

    def renamed(request):
        if request.url.path == "/login/oauth/access_token":
            return httpx.Response(
                200, json=github_tokens("replacement-token", "replacement-refresh")
            )
        return httpx.Response(
            200, json={"id": 12345, "login": "renamed", "name": None, "avatar_url": None}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(renamed)) as provider:
        app.state.oauth.client = provider
        await login(client)
    assert (await client.get("/api/me")).json() == {
        "name": "renamed",
        "avatarUrl": None,
        "githubLinked": True,
    }


async def test_production_cookie_attributes_and_lifetimes(runtime):
    app, client, redis = runtime
    app.state.settings = app.state.settings.model_copy(
        update={"app_env": "prod", "frontend_origin": "https://devon.test"}
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="https://devon.test"
    ) as browser:
        start = await browser.get("/api/auth/github/login")
        state_cookie = start.headers["set-cookie"]
        assert (
            "Secure" in state_cookie
            and "Max-Age=600" in state_cookie
            and "Path=/api/auth/github" in state_cookie
        )
        state = parse_qs(urlsplit(start.headers["location"]).query)["state"][0]
        response = await browser.get(
            "/api/auth/github/callback", params={"state": state, "code": "code"}
        )
        cookies = response.headers.get_list("set-cookie")
        assert all(
            "Secure" in cookie
            and "HttpOnly" in cookie
            and "SameSite=lax" in cookie
            and "Domain=" not in cookie
            for cookie in cookies
        )
        assert any(
            "accessToken=" in cookie and "Max-Age=900" in cookie and "Path=/;" in cookie
            for cookie in cookies
        )
        assert any(
            "refreshToken=" in cookie
            and "Max-Age=1209600" in cookie
            and "Path=/api/auth;" in cookie
            for cookie in cookies
        )
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["referrer-policy"] == "no-referrer"
