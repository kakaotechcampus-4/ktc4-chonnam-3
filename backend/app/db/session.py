"""async engine, AsyncSessionLocal (asyncpg + SQLAlchemy 2.0 async).

docs/db-schema.md / task-02
"""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """프로세스당 하나인 async engine. 입력 없음. 출력: AsyncEngine."""
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.database_url,
            echo=False,
            pool_pre_ping=True,  # 유휴 커넥션이 끊긴 뒤 첫 쿼리가 죽는 것을 막는다
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """AsyncSession 팩토리. 입력 없음. 출력: async_sessionmaker."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,  # commit 후에도 응답 직렬화에서 속성을 읽을 수 있게 둔다
            autoflush=False,
        )
    return _session_factory


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI 의존성. 요청 1건당 세션 1개를 열고 끝나면 닫는다.

    commit 은 service 계층에서만 한다 (docs/layer-rules.md).
    """
    async with get_session_factory()() as session:
        yield session


async def dispose_engine() -> None:
    """engine 커넥션 풀을 정리한다. lifespan 종료와 테스트 teardown 에서 쓴다."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None
