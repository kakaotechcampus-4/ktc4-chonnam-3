"""ARQ 태스크 공통 — worker 세션 컨텍스트."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.session import get_sessionmaker


@asynccontextmanager
async def worker_session(ctx: dict[str, Any]) -> AsyncIterator[AsyncSession]:
    """on_startup 에서 만든 sessionmaker 를 쓰고, 없으면 새로 만든다(테스트 직접 호출)."""
    factory: async_sessionmaker[AsyncSession] = ctx.get("sessionmaker") or get_sessionmaker()
    async with factory() as session:
        yield session
