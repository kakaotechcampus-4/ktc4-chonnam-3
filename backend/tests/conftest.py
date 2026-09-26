"""테스트 DB / Redis 픽스처, httpx AsyncClient(ASGITransport). SQLite 로 대체하지 않는다.

docs/testing.md / task-01

`db` 픽스처는 설정의 PostgreSQL 에 붙어 한 트랜잭션 안에서 create_all 후 테스트를 돌리고
끝나면 rollback 한다. DDL 까지 되돌리므로 어느 DB 에 붙어도 흔적이 남지 않는다.
Redis 픽스처는 필요한 task 에서 추가한다.
"""

from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

import app.db.models  # noqa: F401 — 모든 테이블을 metadata 에 등록
from app.core.config import get_settings
from app.db.base import Base
from app.main import create_app


@pytest.fixture
def app() -> FastAPI:
    """테스트용 FastAPI 앱. get_settings() 캐시를 그대로 쓴다."""
    return create_app()


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    """ASGITransport 기반 AsyncClient. 실제 소켓을 열지 않는다.

    lifespan 은 실행하지 않는다 — 기동 훅이 필요한 테스트는 별도로 감싼다.
    """
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as async_client:
        yield async_client


@pytest.fixture
async def db() -> AsyncIterator[AsyncSession]:
    """PostgreSQL AsyncSession. 테스트가 끝나면 스키마·데이터 모두 rollback 된다.

    service 의 commit 은 savepoint 로 흡수된다 (join_transaction_mode).
    """
    engine = create_async_engine(get_settings().database_url)
    async with engine.connect() as conn:
        await conn.begin()
        await conn.run_sync(Base.metadata.create_all)
        session = AsyncSession(
            bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False
        )
        try:
            yield session
        finally:
            await session.close()
            await conn.rollback()
    await engine.dispose()
