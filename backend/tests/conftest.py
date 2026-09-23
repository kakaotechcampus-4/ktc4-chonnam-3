"""Isolated PostgreSQL/Redis fixtures; never fall back to application credentials."""

import base64
import importlib
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text


@pytest.fixture(scope="session")
def test_database_url():
    value = os.getenv("TEST_DATABASE_URL")
    if not value:
        pytest.skip("Set TEST_DATABASE_URL to an isolated PostgreSQL test database")
    # 아래 fixture가 테이블을 비우므로 앱의 DATABASE_URL로 대체하지 않는다.
    parsed = urlsplit(value)
    if parsed.scheme != "postgresql+asyncpg" or "_test" not in parsed.path:
        raise RuntimeError("TEST_DATABASE_URL must name an isolated PostgreSQL *_test* database")
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "DATABASE_URL": value, "PYTHONUTF8": "1"},
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode:
        raise RuntimeError("Isolated test database migration failed:\n" + result.stderr)
    return value


@pytest.fixture(scope="session")
def test_redis_url():
    value = os.getenv("TEST_REDIS_URL")
    if not value:
        pytest.skip("Set TEST_REDIS_URL to an isolated Redis database (13, 14 or 15)")
    # FLUSHDB가 실제 로그인 세션이나 작업 큐를 지우지 않도록 테스트 DB만 허용한다.
    parsed = urlsplit(value)
    if parsed.scheme != "redis" or parsed.path not in {"/13", "/14", "/15"}:
        raise RuntimeError(
            "TEST_REDIS_URL must explicitly select an isolated database 13, 14 or 15"
        )
    return value


@pytest.fixture
def app_settings(test_database_url, test_redis_url):
    from app.core.config import Settings

    return Settings(
        _env_file=None,
        app_env="local",
        database_url=test_database_url,
        redis_url=test_redis_url,
        frontend_origin="http://localhost:5173",
        github_redirect_uri="http://localhost:5173/auth/github/callback",
        github_client_id="test-client",
        github_client_secret="test-client-secret",
        token_encryption_key=base64.b64encode(bytes(range(32))).decode(),
        cookie_secure=False,
    )


@pytest_asyncio.fixture
async def app(app_settings):
    module = importlib.import_module("app.main")
    assert hasattr(module, "create_app"), "FastAPI application must be implemented"
    application = module.create_app(app_settings)
    async with application.router.lifespan_context(application):
        from app.db.base import Base

        tables = ", ".join('"' + table.name + '"' for table in Base.metadata.sorted_tables)
        async with application.state.session_factory() as session:
            await session.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
            await session.commit()
        await application.state.redis.flushdb()
        yield application
        await application.state.redis.flushdb()


@pytest_asyncio.fixture
async def client(app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://localhost:5173",
        headers={"Origin": "http://localhost:5173"},
        follow_redirects=False,
    ) as instance:
        yield instance


@pytest_asyncio.fixture
async def db(app):
    async with app.state.session_factory() as session:
        yield session


@pytest.fixture
def redis(app):
    return app.state.redis
