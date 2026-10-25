"""저장소 수집과 면접 준비 task를 같은 worker에 등록한다."""

from typing import Any

import httpx
from arq.connections import RedisSettings
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.crypto import TokenCipher
from app.workers.tasks.initial_sync import initial_sync
from app.workers.tasks.interview_prep import interview_prep


async def startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    settings.validate_auth()
    ctx["settings"] = settings
    ctx["engine"] = create_async_engine(settings.database_url, pool_pre_ping=True)
    ctx["session_factory"] = async_sessionmaker(ctx["engine"], expire_on_commit=False)
    ctx["cipher"] = TokenCipher(settings.token_encryption_key.get_secret_value())
    ctx["http_client"] = httpx.AsyncClient(timeout=15, follow_redirects=False)


async def shutdown(ctx: dict[str, Any]) -> None:
    await ctx["http_client"].aclose()
    await ctx["engine"].dispose()


class WorkerSettings:
    functions = [initial_sync, interview_prep]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_tries = 1
    job_timeout = 600
