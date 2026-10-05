"""Browser-test server: real app/database/Redis; only GitHub HTTP is simulated.

Never run against application data. The dedicated database name must end with
``_oauth_browser_test`` and Redis must use database 13 on a test-only instance.
"""

import asyncio
import base64
import hashlib
import os
import subprocess
import sys
from contextlib import asynccontextmanager
from urllib.parse import parse_qs, urlsplit

import httpx
from sqlalchemy import text

from app.core.config import Settings
from app.main import create_app

database_url = os.environ["TEST_DATABASE_URL"]
redis_url = os.environ["TEST_REDIS_URL"]
if (
    urlsplit(database_url).scheme != "postgresql+asyncpg"
    or not urlsplit(database_url).path.endswith("_oauth_browser_test")
    or urlsplit(redis_url).scheme != "redis"
    or urlsplit(redis_url).path != "/13"
):
    raise RuntimeError("Browser tests require a dedicated *_oauth_browser_test DB and Redis /13")

settings = Settings(
    _env_file=None,
    app_env="local",
    database_url=database_url,
    redis_url=redis_url,
    frontend_origin="http://localhost:5173",
    github_redirect_uri="http://localhost:5173/auth/github/callback",
    github_client_id="browser-test-client",
    github_client_secret="browser-test-secret",
    token_encryption_key=base64.b64encode(bytes(range(32))).decode(),
)
app = create_app(settings)
real_lifespan = app.router.lifespan_context


def github(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/login/oauth/access_token":
        form = parse_qs(request.content.decode())
        assert form["redirect_uri"] == [settings.github_redirect_uri]
        verifier = form["code_verifier"][0]
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        assert form["code"] == ["browser_" + challenge.rstrip(b"=").decode()]
        return httpx.Response(
            200,
            json={
                "access_token": "browser-private-github-token",
                "token_type": "bearer",
                "scope": "read:user",
            },
        )
    if request.url.path == "/user":
        return httpx.Response(
            200,
            json={
                "id": 7001,
                "login": "browser-octocat",
                "name": "Browser Octocat",
                "avatar_url": "https://avatars.githubusercontent.com/u/7001",
                "public_repos": 0,
            },
        )
    raise AssertionError(f"Unexpected provider request: {request.url.path}")


@asynccontextmanager
async def lifespan(application):
    await asyncio.to_thread(
        subprocess.run,
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        env={**os.environ, "DATABASE_URL": database_url, "PYTHONUTF8": "1"},
        check=True,
        capture_output=True,
    )
    async with real_lifespan(application):
        async with application.state.session_factory() as db:
            # 위에서 검증한 전용 테스트 DB만 초기화하며 연관 데이터도 함께 비운다.
            await db.execute(text("TRUNCATE users CASCADE"))
            await db.commit()
        await application.state.redis.flushdb()
        async with httpx.AsyncClient(transport=httpx.MockTransport(github)) as outbound:
            application.state.oauth.client = outbound
            yield


app.router.lifespan_context = lifespan
