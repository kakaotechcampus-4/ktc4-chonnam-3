import asyncio
import os
import sys
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.errors import AppError
from app.db.models.user import User
from app.features.auth import service
from tests.features.test_auth_flow import login
from tests.features.test_auth_flow import runtime as runtime


async def rotate(app, token):
    async with app.state.sessions() as session:
        return await service.refresh(session, app.state.tokens, token)


async def revoke(app, token):
    async with app.state.sessions() as session:
        await service.logout(session, app.state.tokens, token)


async def test_login_persists_refresh_identifiers_only_in_postgres(runtime):
    app, client, redis = runtime
    await login(client)
    claims = app.state.tokens.decode(client.cookies.get("refreshToken"), "refresh")
    async with app.state.sessions() as session:
        connection = await session.connection()
        tables = await connection.run_sync(lambda conn: inspect(conn).get_table_names())
        assert "auth_sessions" in tables, "Login must persist its refresh session in PostgreSQL"
        row = (await session.execute(text("SELECT * FROM auth_sessions"))).mappings().one()
        user = await session.get(User, UUID(claims["sub"]))
        assert row["id"] == UUID(claims["sid"])
        assert row["user_id"] == user.id
        assert row["refresh_jti"] == UUID(claims["jti"])
        assert row["generation"] == user.refresh_generation == UUID(claims["generation"])
        assert row["expires_at"] == datetime.fromtimestamp(claims["exp"], UTC)
        assert client.cookies.get("refreshToken") not in str(row)
    assert await redis.keys("auth:refresh:*") == []


@pytest.mark.parametrize("missing", [True, False])
async def test_missing_or_expired_db_session_never_recreates_or_revokes_others(runtime, missing):
    from app.db.models.user import AuthSession

    app, client, redis = runtime
    await login(client)
    old = client.cookies.get("refreshToken")
    claims = app.state.tokens.decode(old, "refresh")
    await login(client)
    other = client.cookies.get("refreshToken")
    async with app.state.sessions() as session:
        record = await session.get(AuthSession, UUID(claims["sid"]))
        if missing:
            await session.delete(record)
        else:
            record.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()
    with pytest.raises(AppError, match="refresh_token_invalid"):
        await rotate(app, old)
    await rotate(app, other)
    async with app.state.sessions() as session:
        user = await session.get(User, UUID(claims["sub"]))
        assert user.refresh_generation == UUID(claims["generation"])
        if missing:
            assert await session.get(AuthSession, UUID(claims["sid"])) is None


async def test_concurrent_refresh_commits_global_replay_revocation(runtime):
    app, client, redis = runtime
    await login(client)
    old = client.cookies.get("refreshToken")
    claims = app.state.tokens.decode(old, "refresh")
    await login(client)
    other = client.cookies.get("refreshToken")
    results = await asyncio.gather(rotate(app, old), rotate(app, old), return_exceptions=True)
    successes = [result for result in results if isinstance(result, tuple)]
    assert len(successes) == 1
    assert sum(isinstance(result, AppError) for result in results) == 1
    async with app.state.sessions() as session:
        user = await session.get(User, UUID(claims["sub"]))
        assert user.refresh_generation != UUID(claims["generation"])
    for invalidated in (successes[0][1], other):
        with pytest.raises(AppError, match="refresh_token_invalid"):
            await rotate(app, invalidated)
    await login(client)
    fresh = client.cookies.get("refreshToken")
    with pytest.raises(AppError, match="refresh_token_invalid"):
        await rotate(app, old)
    await rotate(app, fresh)


async def test_issue_after_replay_refreshes_cached_user_generation(runtime):
    app, client, redis = runtime
    await login(client)
    old = client.cookies.get("refreshToken")
    claims = app.state.tokens.decode(old, "refresh")
    async with app.state.sessions() as cached_session:
        cached_user = await cached_session.get(User, UUID(claims["sub"]))
        await cached_session.commit()
        await rotate(app, old)
        with pytest.raises(AppError, match="refresh_token_invalid"):
            await rotate(app, old)
        assert cached_user.refresh_generation == UUID(claims["generation"])
        pair = await service.issue_tokens(cached_session, app.state.tokens, str(cached_user.id))
    new_claims = app.state.tokens.decode(pair[1], "refresh")
    assert new_claims["generation"] != claims["generation"]
    await rotate(app, pair[1])


async def test_rotation_extends_db_expiry_to_exact_jwt_expiry(runtime):
    from app.db.models.user import AuthSession

    app, client, redis = runtime
    await login(client)
    old = client.cookies.get("refreshToken")
    claims = app.state.tokens.decode(old, "refresh")
    async with app.state.sessions() as session:
        record = await session.get(AuthSession, UUID(claims["sid"]))
        record.expires_at = datetime.now(UTC) + timedelta(seconds=60)
        await session.commit()
    new = app.state.tokens.decode((await rotate(app, old))[1], "refresh")
    async with app.state.sessions() as session:
        record = await session.get(AuthSession, UUID(claims["sid"]))
        assert record.expires_at == datetime.fromtimestamp(new["exp"], UTC)
        assert record.expires_at > datetime.now(UTC) + timedelta(days=13)


@pytest.mark.parametrize("logout_first", [True, False])
async def test_logout_revokes_sid_even_if_refresh_has_rotated(runtime, logout_first):
    from app.db.models.user import AuthSession

    app, client, redis = runtime
    await login(client)
    old = client.cookies.get("refreshToken")
    claims = app.state.tokens.decode(old, "refresh")
    await login(client)
    other = client.cookies.get("refreshToken")
    if logout_first:
        await revoke(app, old)
        invalid = old
    else:
        invalid = (await rotate(app, old))[1]
        await revoke(app, old)
    with pytest.raises(AppError, match="refresh_token_invalid"):
        await rotate(app, invalid)
    await rotate(app, other)
    async with app.state.sessions() as session:
        assert await session.get(AuthSession, UUID(claims["sid"])) is None


async def test_concurrent_logout_refresh_cannot_leave_session_alive(runtime):
    from app.db.models.user import AuthSession

    app, client, redis = runtime
    await login(client)
    old = client.cookies.get("refreshToken")
    claims = app.state.tokens.decode(old, "refresh")
    results = await asyncio.gather(rotate(app, old), revoke(app, old), return_exceptions=True)
    assert results[1] is None
    assert isinstance(results[0], tuple) or isinstance(results[0], AppError)
    async with app.state.sessions() as session:
        assert await session.get(AuthSession, UUID(claims["sid"])) is None
    if isinstance(results[0], tuple):
        with pytest.raises(AppError, match="refresh_token_invalid"):
            await rotate(app, results[0][1])


async def test_redis_loss_and_legacy_keys_do_not_authorize_refresh(runtime):
    app, client, redis = runtime
    await login(client)
    current = client.cookies.get("refreshToken")
    claims = app.state.tokens.decode(current, "refresh")
    await redis.flushdb()
    current = (await rotate(app, current))[1]
    legacy_sid, legacy_generation, legacy_jti = (str(uuid4()) for _ in range(3))
    legacy = app.state.tokens.encode(
        claims["sub"], "refresh", sid=legacy_sid, generation=legacy_generation, jti=legacy_jti
    )
    await redis.set(f"auth:refresh:user:{claims['sub']}", legacy_generation, ex=1209600)
    await redis.hset(
        f"auth:refresh:session:{legacy_sid}",
        mapping={"user_id": claims["sub"], "generation": legacy_generation, "jti": legacy_jti},
    )
    with pytest.raises(AppError, match="refresh_token_invalid"):
        await rotate(app, legacy)
    await rotate(app, current)
    assert await redis.get(f"auth:refresh:user:{claims['sub']}") == legacy_generation


async def test_cleanup_removes_expired_sessions_only_and_is_idempotent(runtime):
    from app.db.models.user import AuthSession

    app, client, redis = runtime
    await login(client)
    expired = app.state.tokens.decode(client.cookies.get("refreshToken"), "refresh")
    await login(client)
    active = client.cookies.get("refreshToken")
    async with app.state.sessions() as session:
        record = await session.get(AuthSession, UUID(expired["sid"]))
        record.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()
    async with app.state.sessions() as session:
        assert await service.cleanup_expired_sessions(session) == 1
    async with app.state.sessions() as session:
        assert await service.cleanup_expired_sessions(session) == 0
        assert len((await session.scalars(select(AuthSession))).all()) == 1
    await rotate(app, active)


async def test_cleanup_cli_requires_database_only_and_changes_real_rows(runtime):
    from app.db.models.user import AuthSession

    app, client, redis = runtime
    await login(client)
    async with app.state.sessions() as session:
        record = await session.scalar(select(AuthSession))
        record.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("GITHUB_", "JWT_", "TOKEN_ENCRYPTION_"))
    }
    env["DATABASE_URL"] = app.state.settings.database_url
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "scripts.cleanup_auth_sessions",
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    assert process.returncode == 0, stderr.decode()
    assert stdout.decode().strip() == "Deleted 1 expired auth session(s)."
    assert "gho_" not in (stdout + stderr).decode()
    async with app.state.sessions() as session:
        assert (await session.scalars(select(AuthSession))).all() == []


async def test_database_connection_outage_returns_503_without_clearing_valid_cookies(runtime):
    app, client, redis = runtime
    await login(client)
    engine = create_async_engine(
        "postgresql+asyncpg://devon@127.0.0.1:1/devon_oauth_test", connect_args={"timeout": 0.1}
    )
    app.state.sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app, raise_app_exceptions=False),
            base_url=app.state.settings.frontend_origin,
            cookies=client.cookies,
        ) as browser:
            for route in ("refresh", "logout"):
                response = await browser.post(
                    f"/api/auth/{route}", headers={"Origin": app.state.settings.frontend_origin}
                )
                assert response.status_code == 503
                assert response.json()["error"]["reason"] == "service_unavailable"
                assert "set-cookie" not in response.headers
            assert (await browser.get("/api/me")).status_code == 503
            for token in (None, "invalid"):
                browser.cookies.clear()
                if token:
                    browser.cookies.set("refreshToken", token)
                response = await browser.post(
                    "/api/auth/logout", headers={"Origin": app.state.settings.frontend_origin}
                )
                assert response.status_code == 204
                assert "Max-Age=0" in response.headers["set-cookie"]
            start = await browser.get("/api/auth/github/login")
            from urllib.parse import parse_qs, urlsplit

            state = parse_qs(urlsplit(start.headers["location"]).query)["state"][0]
            callback = await browser.get(
                "/api/auth/github/callback", params={"state": state, "code": "code"}
            )
            assert callback.headers["location"].endswith("/login?error=service_unavailable")
    finally:
        await engine.dispose()


async def test_cleanup_cli_fails_safely_when_database_unavailable():
    env = {
        **os.environ,
        "DATABASE_URL": "postgresql+asyncpg://devon:private-password@127.0.0.1:1/devon_oauth_test",
    }
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "scripts.cleanup_auth_sessions",
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    assert process.returncode != 0
    assert not stdout
    assert stderr.decode(errors="replace").strip() == "Auth session cleanup failed."
