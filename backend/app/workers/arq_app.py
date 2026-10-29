"""Initial repository synchronization worker; AI tasks remain unregistered."""

from typing import Any

import httpx
from arq.connections import RedisSettings
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.crypto import TokenCipher
from app.workers.tasks.initial_sync import initial_sync


async def startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    settings.validate_auth()
    ctx["engine"] = create_async_engine(settings.database_url, pool_pre_ping=True)
    ctx["session_factory"] = async_sessionmaker(ctx["engine"], expire_on_commit=False)
    ctx["cipher"] = TokenCipher(settings.token_encryption_key.get_secret_value())
    ctx["http_client"] = httpx.AsyncClient(timeout=15, follow_redirects=False)


async def shutdown(ctx: dict[str, Any]) -> None:
    await ctx["http_client"].aclose()
    await ctx["engine"].dispose()


class WorkerSettings:
    functions = [initial_sync]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_tries = 1
    job_timeout = 600
