"""브라우저 콜백은 안전한 오류 안내로 이동하고 기존 인증 경계를 보존한다."""

import httpx
import pytest
from redis.exceptions import ConnectionError
from sqlalchemy import func, select

from app.db.models.user import User


@pytest.mark.parametrize(
    "status,payload,display_code",
    [
        (400, {"error": "bad_verification_code"}, "invalid_code"),
        (503, {"message": "private-provider-detail"}, "provider_unavailable"),
        (
            200,
            {
                "access_token": "private-provider-token",
                "token_type": "bearer",
                "scope": "read:user",
                "expires_in": 3600,
            },
            "provider_configuration",
        ),
    ],
)
@pytest.mark.parametrize("purpose", ["login", "link"])
async def test_provider_failure_preserves_session_boundary(
    client, app, db, redis, status, payload, display_code, purpose
):
    user = None
    sid = None
    if purpose == "link":
        user = User(name="Existing member", status="active")
        db.add(user)
        await db.commit()
        sid = await app.state.sessions.create(user.id)
    state, _ = await app.state.oauth_states.create(purpose, user.id if user else None)
    cookie_header = f"oauthState={state}" + (f"; devon_session={sid}" if sid else "")
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(status, json=payload))
    ) as provider:
        app.state.oauth.client = provider
        response = await client.get(
            "/api/auth/github/callback",
            params={"state": state, "code": "private-authorization-code"},
            headers={"cookie": cookie_header},
        )

    assert response.status_code == 302
    expected = f"/login?error={display_code}" + ("&flow=link" if user else "")
    assert response.headers["location"] == expected
    assert "no-store" in response.headers["cache-control"]
    assert response.headers["referrer-policy"] == "no-referrer"
    cookie = next(c for c in response.headers.get_list("set-cookie") if c.startswith("oauthState="))
    assert "Max-Age=0" in cookie and "Path=/auth/github" in cookie
    assert await redis.get(f"auth:oauth:{state}") is None
    assert len(await redis.keys("auth:sess:*")) == (1 if user else 0)
    assert await db.scalar(select(func.count()).select_from(User)) == (1 if user else 0)
    if user:
        assert await app.state.sessions.get(sid) == user.id
    assert "private-" not in str(response.headers) + response.text


async def test_missing_code_redirects_after_consuming_state(client, app, redis):
    state, _ = await app.state.oauth_states.create("login")
    response = await client.get(
        "/api/auth/github/callback",
        params={"state": state},
        headers={"cookie": f"oauthState={state}"},
    )
    assert response.status_code == 302
    assert response.headers["location"] == "/login?error=invalid_code"
    assert await redis.get(f"auth:oauth:{state}") is None


@pytest.mark.parametrize("denied", [True, False])
async def test_link_error_retains_session_and_retries_link(client, app, db, redis, denied):
    user = User(name="Existing member", status="active")
    db.add(user)
    await db.commit()
    sid = await app.state.sessions.create(user.id)
    state, _ = await app.state.oauth_states.create("link", user.id)
    params = {"state": state, "error": "access_denied"} if denied else {"state": state}
    response = await client.get(
        "/api/auth/github/callback",
        params=params,
        headers={"cookie": f"oauthState={state}; devon_session={sid}"},
    )
    assert response.status_code == 302
    expected = "/login?error=denied&flow=link" if denied else "/login?error=invalid_code&flow=link"
    assert response.headers["location"] == expected
    assert await app.state.sessions.get(sid) == user.id
    assert len(await redis.keys("auth:sess:*")) == 1
    assert await redis.get(f"auth:oauth:{state}") is None


async def test_invalid_state_does_not_trust_query_retry_flow(client):
    response = await client.get("/api/auth/github/callback?state=invalid&code=secret&flow=link")
    assert response.status_code == 302
    assert response.headers["location"] == "/login?error=invalid_state"
    assert "devon_session" not in response.cookies


async def test_callback_redis_outage_keeps_server_error(client, app, monkeypatch):
    state, _ = await app.state.oauth_states.create("login")

    async def unavailable(*args, **kwargs):
        raise ConnectionError("private-redis-error")

    monkeypatch.setattr(app.state.oauth_states.redis, "getdel", unavailable)
    response = await client.get(
        "/api/auth/github/callback",
        params={"state": state, "code": "code"},
        headers={"cookie": f"oauthState={state}"},
    )
    assert response.status_code == 500
    assert response.json()["error"]["reason"] == "internal_error"
    assert "location" not in response.headers
    assert "private-redis-error" not in response.text
    assert "Max-Age=0" in response.headers["set-cookie"]
