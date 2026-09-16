import asyncio
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs
from uuid import UUID

import httpx
import pytest
from sqlalchemy import select

from app.core.errors import AppError
from app.db.models.user import GitHubAccount, User
from tests.features.test_auth_flow import github_tokens, login
from tests.features.test_auth_flow import runtime as runtime


async def signed_in(runtime):
    app, client, _ = runtime
    await login(client)
    return UUID(app.state.tokens.decode(client.cookies.get("accessToken"), "access")["sub"])


async def expire_access(app, user_id, *, refresh_expired=False, legacy=False, expires_in=-1):
    async with app.state.sessions() as session:
        account = await session.scalar(
            select(GitHubAccount).where(GitHubAccount.user_id == user_id)
        )
        account.token_expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)
        if refresh_expired:
            account.refresh_token_expires_at = datetime.now(UTC) - timedelta(seconds=1)
        if legacy:
            account.token_expires_at = None
            account.refresh_token_encrypted = None
            account.refresh_token_expires_at = None
        await session.commit()


async def test_expiring_login_encrypts_both_secrets_and_logout_preserves_github_connection(runtime):
    app, client, _ = runtime
    user_id = await signed_in(runtime)
    async with app.state.sessions() as session:
        account = await session.scalar(
            select(GitHubAccount).where(GitHubAccount.user_id == user_id)
        )
        assert app.state.cipher.decrypt(account.refresh_token_encrypted) == "ghr_private"
        assert datetime.now(UTC) + timedelta(hours=7) < account.token_expires_at
    response = await client.post(
        "/api/auth/logout", headers={"Origin": app.state.settings.frontend_origin}
    )
    assert response.status_code == 204
    async with app.state.sessions() as session:
        account = await session.scalar(
            select(GitHubAccount).where(GitHubAccount.user_id == user_id)
        )
        assert account.token_status == "valid"
        assert account.refresh_token_encrypted is not None


@pytest.mark.parametrize("legacy", [False, True])
async def test_valid_token_calls_api_without_refresh(runtime, legacy):
    app, _, _ = runtime
    user_id = await signed_in(runtime)
    if legacy:
        await expire_access(app, user_id, legacy=True)

    def github(request):
        assert request.url.host == "api.github.com"
        assert request.headers["authorization"] == "Bearer gho_private"
        return httpx.Response(200, json={"id": 12345})

    async with httpx.AsyncClient(transport=httpx.MockTransport(github)) as provider:
        app.state.github.client.client = provider
        assert await app.state.github.get(user_id, "/user") == {"id": 12345}


@pytest.mark.parametrize("expires_in", [-1, 30])
async def test_expired_or_soon_expiring_token_rotates_once_across_concurrent_api_calls(
    runtime, expires_in
):
    app, _, _ = runtime
    user_id = await signed_in(runtime)
    await expire_access(app, user_id, expires_in=expires_in)
    rotations = []

    async def github(request):
        if request.url.path == "/login/oauth/access_token":
            form = parse_qs(request.content.decode())
            assert form["refresh_token"] == ["ghr_private"]
            assert form["grant_type"] == ["refresh_token"]
            rotations.append(form)
            await asyncio.sleep(0.05)
            return httpx.Response(200, json=github_tokens("new-access", "new-refresh"))
        assert request.headers["authorization"] == "Bearer new-access"
        return httpx.Response(200, json={"id": 12345})

    async with httpx.AsyncClient(transport=httpx.MockTransport(github)) as provider:
        app.state.oauth.client = provider
        app.state.github.client.client = provider
        results = await asyncio.gather(*(app.state.github.get(user_id, "/user") for _ in range(5)))
    assert results == [{"id": 12345}] * 5
    assert len(rotations) == 1
    async with app.state.sessions() as session:
        account = await session.scalar(
            select(GitHubAccount).where(GitHubAccount.user_id == user_id)
        )
        assert app.state.cipher.decrypt(account.access_token_encrypted) == "new-access"
        assert app.state.cipher.decrypt(account.refresh_token_encrypted) == "new-refresh"
        assert account.token_expires_at > datetime.now(UTC) + timedelta(hours=7)
        assert account.refresh_token_expires_at > datetime.now(UTC) + timedelta(days=100)


@pytest.mark.parametrize("failure", ["expired", "bad_refresh_token", "api_401"])
async def test_revocation_is_committed_without_invalidating_devon_login(runtime, failure):
    app, client, _ = runtime
    user_id = await signed_in(runtime)
    original_provider = app.state.oauth.client
    if failure != "api_401":
        await expire_access(app, user_id, refresh_expired=failure == "expired")

    def github(request):
        assert failure != "expired", "An expired refresh token must not be submitted"
        if request.url.path == "/login/oauth/access_token":
            return httpx.Response(200, json={"error": "bad_refresh_token"})
        return httpx.Response(401, json={"message": "Bad credentials"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(github)) as provider:
        app.state.oauth.client = provider
        app.state.github.client.client = provider
        with pytest.raises(AppError, match="token_invalid"):
            await app.state.github.get(user_id, "/user")
        with pytest.raises(AppError, match="token_invalid"):
            await app.state.github.get(user_id, "/user")
    async with app.state.sessions() as session:
        account = await session.scalar(
            select(GitHubAccount).where(GitHubAccount.user_id == user_id)
        )
        assert account.token_status == "revoked"
    me = await client.get("/api/me")
    assert me.status_code == 200 and me.json()["githubLinked"] is False
    assert (
        await client.post(
            "/api/auth/refresh", headers={"Origin": app.state.settings.frontend_origin}
        )
    ).status_code == 204
    app.state.oauth.client = original_provider
    await login(client)
    assert (await client.get("/api/me")).json()["githubLinked"] is True


@pytest.mark.parametrize("failure", ["network", "rate_limit", "server", "malformed"])
async def test_transient_refresh_failure_keeps_record_for_retry(runtime, failure):
    app, _, _ = runtime
    user_id = await signed_in(runtime)
    await expire_access(app, user_id)

    def github(request):
        if failure == "network":
            raise httpx.ReadTimeout("sensitive-provider-response")
        if failure == "malformed":
            return httpx.Response(200, json={"access_token": "sensitive-provider-response"})
        return httpx.Response(
            429 if failure == "rate_limit" else 503, json={"error": "bad_refresh_token"}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(github)) as provider:
        app.state.oauth.client = provider
        with pytest.raises(AppError, match="provider_unavailable") as error:
            await app.state.github.get(user_id, "/user")
    assert error.value.status == 503
    assert "sensitive" not in str(error.value)
    async with app.state.sessions() as session:
        account = await session.scalar(
            select(GitHubAccount).where(GitHubAccount.user_id == user_id)
        )
        assert account.token_status == "valid"
        assert app.state.cipher.decrypt(account.refresh_token_encrypted) == "ghr_private"


async def test_late_401_from_previous_token_cannot_revoke_relogin(runtime):
    app, client, _ = runtime
    user_id = await signed_in(runtime)
    in_flight, release = asyncio.Event(), asyncio.Event()

    async def github(request):
        if request.headers["authorization"] == "Bearer gho_private":
            in_flight.set()
            await release.wait()
            return httpx.Response(401)
        assert request.headers["authorization"] == "Bearer replacement"
        return httpx.Response(200, json={"id": 12345})

    async with httpx.AsyncClient(transport=httpx.MockTransport(github)) as provider:
        app.state.github.client.client = provider
        pending = asyncio.create_task(app.state.github.get(user_id, "/user"))
        await asyncio.wait_for(in_flight.wait(), 5)
        # 다른 콜백이 별도 트랜잭션으로 토큰을 교체하고 커밋한 상황을 재현한다.
        async with app.state.sessions() as session:
            account = await session.scalar(
                select(GitHubAccount).where(GitHubAccount.user_id == user_id)
            )
            account.access_token_encrypted = app.state.cipher.encrypt("replacement")
            await session.commit()
        release.set()
        assert await asyncio.wait_for(pending, 5) == {"id": 12345}
    assert (await client.get("/api/me")).json()["githubLinked"] is True


async def test_me_does_not_claim_expired_unrefreshable_connection_is_linked(runtime):
    app, client, _ = runtime
    user_id = await signed_in(runtime)
    await expire_access(app, user_id, refresh_expired=True)
    assert (await client.get("/api/me")).json()["githubLinked"] is False


async def test_blocked_user_cannot_use_github_api(runtime):
    app, _, _ = runtime
    user_id = await signed_in(runtime)
    async with app.state.sessions() as session:
        user = await session.get(User, user_id)
        user.status = "suspended"
        await session.commit()
    with pytest.raises(AppError, match="account_suspended"):
        await app.state.github.get(user_id, "/user")


async def test_expired_refresh_does_not_discard_still_usable_access(runtime):
    app, client, _ = runtime
    user_id = await signed_in(runtime)
    await expire_access(app, user_id, refresh_expired=True, expires_in=30)
    assert (await client.get("/api/me")).json()["githubLinked"] is True

    def github(request):
        assert request.url.path == "/user", "Expired refresh credentials must not be submitted"
        assert request.headers["authorization"] == "Bearer gho_private"
        return httpx.Response(200, json={"id": 12345})

    async with httpx.AsyncClient(transport=httpx.MockTransport(github)) as provider:
        app.state.oauth.client = provider
        app.state.github.client.client = provider
        assert await app.state.github.get(user_id, "/user") == {"id": 12345}


async def test_cipher_corruption_is_service_error_not_provider_revocation(runtime):
    app, client, _ = runtime
    user_id = await signed_in(runtime)
    async with app.state.sessions() as session:
        account = await session.scalar(
            select(GitHubAccount).where(GitHubAccount.user_id == user_id)
        )
        account.access_token_encrypted = b"damaged-ciphertext"
        await session.commit()
    with pytest.raises(AppError, match="service_unavailable") as error:
        await app.state.github.get(user_id, "/user")
    assert error.value.status == 503
    async with app.state.sessions() as session:
        account = await session.scalar(
            select(GitHubAccount).where(GitHubAccount.user_id == user_id)
        )
        assert account.token_status == "valid"


async def test_expired_access_with_live_refresh_still_counts_as_linked(runtime):
    app, client, _ = runtime
    user_id = await signed_in(runtime)
    await expire_access(app, user_id)
    assert (await client.get("/api/me")).json()["githubLinked"] is True


async def test_relogin_waits_for_inflight_refresh_then_replaces_its_pair(runtime):
    app, client, _ = runtime
    user_id = await signed_in(runtime)
    await expire_access(app, user_id)
    refreshing, identified, release = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def github(request):
        if request.url.path == "/login/oauth/access_token":
            form = parse_qs(request.content.decode())
            if "refresh_token" in form:
                refreshing.set()
                await release.wait()
                return httpx.Response(200, json=github_tokens("rotated", "rotated-refresh"))
            return httpx.Response(200, json=github_tokens("relogin", "relogin-refresh"))
        if request.headers["authorization"] == "Bearer relogin":
            identified.set()
        return httpx.Response(200, json={"id": 12345, "login": "octo"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(github)) as provider:
        app.state.oauth.client = provider
        app.state.github.client.client = provider
        running = asyncio.create_task(app.state.github.get(user_id, "/user"))
        await asyncio.wait_for(refreshing.wait(), 5)
        callback = asyncio.create_task(login(client))
        await asyncio.wait_for(identified.wait(), 5)
        try:
            await asyncio.sleep(0.05)
            assert not callback.done(), "Callback must wait for the same GitHub account row lock"
        finally:
            release.set()
            await asyncio.wait_for(asyncio.gather(running, callback), 5)
    async with app.state.sessions() as session:
        account = await session.scalar(
            select(GitHubAccount).where(GitHubAccount.user_id == user_id)
        )
        assert app.state.cipher.decrypt(account.access_token_encrypted) == "relogin"
        assert app.state.cipher.decrypt(account.refresh_token_encrypted) == "relogin-refresh"
