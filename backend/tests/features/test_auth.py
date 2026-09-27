import asyncio
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from fastapi import Depends, WebSocket
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy import func, select


@pytest.fixture
async def github(app):
    profile = {
        "id": 1001,
        "login": "octocat",
        "name": "Octo",
        "avatar_url": "https://avatars.githubusercontent.com/u/1001",
        "public_repos": 3,
    }

    def handle(request):
        if request.url.path == "/login/oauth/access_token":
            return httpx.Response(
                200,
                json={
                    "access_token": "github-private-token",
                    "token_type": "bearer",
                    "scope": "read:user",
                },
            )
        if request.url.path == "/user":
            return httpx.Response(200, json=profile)
        raise AssertionError(f"Unexpected GitHub request path: {request.url.path}")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as outbound:
        app.state.oauth.client = outbound
        yield profile


async def login(client):
    start = await client.get("/api/auth/github/login")
    assert start.status_code == 302
    state = parse_qs(urlsplit(start.headers["location"]).query)["state"][0]
    return await client.get(
        "/api/auth/github/callback",
        params={"code": "code", "state": state},
        headers={"cookie": f"oauthState={state}"},
    )


async def test_login_encrypts_token_rotates_session_and_enqueues_sync(
    client, app, db, redis, github
):
    from app.db.models.user import GithubAccount, User

    response = await login(client)
    assert response.status_code == 302
    assert response.headers["location"] == "/home"
    sid = response.cookies["devon_session"]
    cookies = response.headers.get_list("set-cookie")
    session_cookie = next(value for value in cookies if value.startswith("devon_session="))
    assert "HttpOnly" in session_cookie and "Path=/" in session_cookie
    assert "Max-Age=1209600" in session_cookie and "SameSite=lax" in session_cookie
    account = (await db.scalars(select(GithubAccount))).one()
    user = (await db.scalars(select(User))).one()
    assert account.user_id == user.id
    assert account.access_token_encrypted != b"github-private-token"
    assert app.state.cipher.decrypt(account.access_token_encrypted) == "github-private-token"
    assert await redis.get(f"auth:sess:{sid}") == str(user.id).encode()
    assert b"github-private-token" not in response.content
    assert "github-private-token" not in str(response.headers)
    assert len(await redis.zrange("arq:queue", 0, -1)) == 1
    # A second sign-in refreshes the mutable login name without creating another user.
    github["login"] = "renamed"
    start = await client.get("/api/auth/github/login")
    state = parse_qs(urlsplit(start.headers["location"]).query)["state"][0]
    response = await client.get(
        "/api/auth/github/callback",
        params={"code": "again", "state": state},
        headers={"cookie": f"oauthState={state}; devon_session={sid}"},
    )
    assert response.status_code == 302
    assert response.cookies["devon_session"] != sid
    assert await redis.get(f"auth:sess:{sid}") is None
    assert await db.scalar(select(func.count()).select_from(User)) == 1
    await db.refresh(account)
    assert account.login == "renamed"


async def test_wrong_browser_replay_and_wrong_purpose_do_not_login(client, redis, github):
    start = await client.get("/api/auth/github/login")
    state = parse_qs(urlsplit(start.headers["location"]).query)["state"][0]
    response = await client.get(
        "/api/auth/github/callback",
        params={"code": "code", "state": state},
        headers={"cookie": "oauthState=other"},
    )
    assert response.status_code == 302
    assert response.headers["location"] == "/login?error=invalid_state"
    response = await client.get(
        "/api/auth/github/callback",
        params={"code": "code", "state": state},
        headers={"cookie": f"oauthState={state}"},
    )
    assert response.status_code == 302
    replay = await client.get(
        "/api/auth/github/callback",
        params={"code": "code", "state": state},
        headers={"cookie": f"oauthState={state}"},
    )
    assert replay.status_code == 302
    assert replay.headers["location"] == "/login?error=invalid_state"
    assert "devon_session" not in replay.cookies
    assert len(await redis.keys("auth:sess:*")) == 1


async def test_denial_consumes_state_and_redirects_without_code(client, redis):
    start = await client.get("/api/auth/github/login")
    state = parse_qs(urlsplit(start.headers["location"]).query)["state"][0]
    response = await client.get(
        "/api/auth/github/callback",
        params={"error": "access_denied", "state": state},
        headers={"cookie": f"oauthState={state}"},
    )
    assert response.status_code == 302
    assert response.headers["location"] == "/login?error=denied"
    assert await redis.get(f"auth:oauth:{state}") is None
    assert "Max-Age=0" in response.headers["set-cookie"]


@pytest.mark.parametrize(
    "status,reason", [("suspended", "account_suspended"), ("withdrawn", "account_withdrawn")]
)
async def test_blocked_accounts_cannot_login_or_access_api(client, db, github, status, reason):
    from app.db.models.user import User

    await login(client)
    user = (await db.scalars(select(User))).one()
    user.status = status
    await db.commit()
    response = await client.get("/api/me")
    assert response.status_code == 403
    assert response.json()["error"]["reason"] == reason
    response = await login(client)
    assert response.status_code == 302
    assert response.headers["location"] == f"/login?error={reason}"
    assert "devon_session" not in response.cookies


async def test_logout_is_idempotent_and_retains_github_token(client, db, redis, github):
    from app.db.models.user import GithubAccount

    response = await login(client)
    sid = response.cookies["devon_session"]
    assert (await client.post("/api/auth/logout")).status_code == 204
    assert await redis.get(f"auth:sess:{sid}") is None
    assert (await client.post("/api/auth/logout")).status_code == 204
    assert (await client.get("/api/me")).status_code == 401
    assert (await db.scalars(select(GithubAccount))).one().token_status == "valid"


async def test_relink_requires_session_and_cannot_change_account(client, db, app, github):
    from app.db.models.user import GithubAccount

    unauthenticated = await client.get("/api/auth/github/link")
    assert unauthenticated.status_code == 302
    assert unauthenticated.headers["location"] == "/login"
    response = await login(client)
    sid = response.cookies["devon_session"]
    account = (await db.scalars(select(GithubAccount))).one()
    old_token = account.access_token_encrypted
    start = await client.get("/api/auth/github/link")
    state = parse_qs(urlsplit(start.headers["location"]).query)["state"][0]
    github["id"] = 9999
    response = await client.get(
        "/api/auth/github/link/callback",
        params={"code": "code", "state": state},
        headers={"cookie": f"oauthState={state}; devon_session={sid}"},
    )
    assert response.status_code == 302
    assert response.headers["location"] == "/login?error=github_already_linked&flow=link"
    await db.refresh(account)
    assert account.github_user_id == 1001
    assert account.access_token_encrypted == old_token
    assert await app.state.sessions.get(sid) == account.user_id


async def test_canonical_relink_keeps_session_and_legacy_link_rejects_login_state(
    client, db, github
):
    from app.db.models.user import GithubAccount

    response = await login(client)
    sid = response.cookies["devon_session"]
    account = (await db.scalars(select(GithubAccount))).one()
    account.token_status = "revoked"
    await db.commit()
    start = await client.get("/api/auth/github/login")
    state = parse_qs(urlsplit(start.headers["location"]).query)["state"][0]
    wrong = await client.get(
        "/api/auth/github/link/callback",
        params={"code": "code", "state": state},
        headers={"cookie": f"oauthState={state}; devon_session={sid}"},
    )
    assert wrong.status_code == 302
    assert wrong.headers["location"] == "/login?error=invalid_state"
    start = await client.get("/api/auth/github/link")
    state = parse_qs(urlsplit(start.headers["location"]).query)["state"][0]
    response = await client.get(
        "/api/auth/github/callback",
        params={"code": "code", "state": state},
        headers={"cookie": f"oauthState={state}; devon_session={sid}"},
    )
    assert response.status_code == 302
    assert response.cookies["devon_session"] == sid
    await db.refresh(account)
    assert account.token_status == "valid"


async def test_canonical_link_callback_cannot_turn_expired_session_into_login(
    client, app, redis, github
):
    response = await login(client)
    sid = response.cookies["devon_session"]
    start = await client.get("/api/auth/github/link")
    state = parse_qs(urlsplit(start.headers["location"]).query)["state"][0]
    await app.state.sessions.delete(sid)
    response = await client.get(
        "/api/auth/github/callback",
        params={"code": "code", "state": state},
        headers={"cookie": f"oauthState={state}; devon_session={sid}"},
    )
    assert response.status_code == 302
    assert response.headers["location"] == "/login"
    assert "devon_session" not in response.cookies
    assert await redis.keys("auth:sess:*") == []


async def test_canonical_link_callback_is_bound_to_starting_user(client, app, db, github):
    from app.db.models.user import User

    await login(client)
    start = await client.get("/api/auth/github/link")
    state = parse_qs(urlsplit(start.headers["location"]).query)["state"][0]
    other = User(name="Other", status="active")
    db.add(other)
    await db.commit()
    sid = await app.state.sessions.create(other.id)
    response = await client.get(
        "/api/auth/github/callback",
        params={"code": "code", "state": state},
        headers={"cookie": f"oauthState={state}; devon_session={sid}"},
    )
    assert response.status_code == 302
    assert response.headers["location"] == "/login?error=invalid_state"
