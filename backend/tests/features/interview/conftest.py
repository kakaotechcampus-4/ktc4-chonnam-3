"""면접 테스트 PostgreSQL fixture. SQLite 로 대체하지 않는다.

앱 DATABASE_URL 로 대체하지 않고 이름에 _test 가 들어간 TEST_DATABASE_URL 만 쓴다 (없으면 skip).
한 트랜잭션 안에서 create_all 후 테스트를 돌리고 끝나면 rollback 한다 — DDL 까지 되돌린다.
ponytail: 공용 db fixture(task-06, PR #57)가 develop 에 들어오면 이 파일을 지우고 합친다.

task-13
"""

import os
from collections.abc import AsyncIterator
from urllib.parse import urlsplit

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

import app.db.models  # noqa: F401 — 모든 테이블을 metadata 에 등록
from app.db.base import Base


@pytest.fixture(scope="session")
def test_database_url() -> str:
    value = os.getenv("TEST_DATABASE_URL")
    if not value:
        pytest.skip("TEST_DATABASE_URL 에 격리된 PostgreSQL *_test DB 를 지정하세요")
    parsed = urlsplit(value)
    if parsed.scheme != "postgresql+asyncpg" or "_test" not in parsed.path:
        raise RuntimeError("TEST_DATABASE_URL 은 postgresql+asyncpg 의 *_test DB 여야 합니다")
    return value


@pytest.fixture
async def db(test_database_url: str) -> AsyncIterator[AsyncSession]:
    """service 의 commit 은 savepoint 로 흡수된다 (join_transaction_mode)."""
    engine = create_async_engine(test_database_url)
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
