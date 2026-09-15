"""async engine, AsyncSessionLocal (asyncpg + SQLAlchemy 2.0 async).

docs/db-schema.md / task-02
"""

from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings


@lru_cache(maxsize=1)
def get_engine() -> AsyncEngine:
    """프로세스 단위 engine. API 와 ARQ worker 가 각각 하나씩 가진다."""
    settings = get_settings()
    return create_async_engine(settings.database_url, pool_pre_ping=True, future=True)


@lru_cache(maxsize=1)
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """commit 책임은 service/pipeline 에 있다. autoflush 는 끈다."""
    return async_sessionmaker(
        bind=get_engine(),
        expire_on_commit=False,
        autoflush=False,
    )


async def session_scope() -> AsyncIterator[AsyncSession]:
    """worker/스크립트용 세션 컨텍스트. FastAPI 는 core/deps.py 의 get_db 를 쓴다."""
    async with get_sessionmaker()() as session:
        yield session
