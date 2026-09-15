"""테스트 DB / Redis 픽스처, httpx AsyncClient(ASGITransport). SQLite 로 대체하지 않는다.

DB 를 쓰는 테스트는 PostgreSQL 이 없으면 skip 한다 (docs/testing.md: SQLite 대체 금지).
로컬에서는 `docker compose up -d db redis` 후 실행한다.

docs/testing.md / task-01
"""

import os
import uuid
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.deps import current_user, get_arq, get_db
from app.db import models  # noqa: F401 - metadata 등록
from app.db.base import Base
from app.db.models.user import User
from app.main import create_app

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://devon:devon@localhost:5432/devon_test"
)


class FakeRedis:
    """락/mirror/publish 만 쓰는 최소 Redis 대역 (테스트가 Redis 기동에 매이지 않도록)."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.hashes: dict[str, dict[str, str]] = {}
        self.published: list[tuple[str, str]] = []

    async def set(
        self, key: str, value: str, *, nx: bool = False, ex: int | None = None
    ) -> bool | None:
        if nx and key in self.store:
            return None
        self.store[key] = value
        return True

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def delete(self, key: str) -> int:
        return 1 if self.store.pop(key, None) is not None else 0

    async def hset(self, key: str, *, mapping: dict[str, str]) -> int:
        self.hashes.setdefault(key, {}).update(mapping)
        return len(mapping)

    async def expire(self, key: str, seconds: int) -> bool:
        return key in self.store or key in self.hashes

    async def publish(self, channel: str, message: str) -> int:
        self.published.append((channel, message))
        return 1


class FakeArq:
    """enqueue 호출만 기록하는 ARQ 대역."""

    def __init__(self) -> None:
        self.jobs: list[tuple[str, tuple[object, ...]]] = []

    async def enqueue_job(self, name: str, *args: object, **_: object) -> None:
        self.jobs.append((name, args))


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(scope="session")
def settings():  # type: ignore[no-untyped-def]
    get_settings.cache_clear()
    return get_settings()


@pytest.fixture
async def db_engine():  # type: ignore[no-untyped-def]
    """테스트 DB 스키마를 만든다. 연결이 안 되면 skip."""
    engine = create_async_engine(TEST_DATABASE_URL, future=True)
    try:
        async with engine.begin() as conn:
            await conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS pgcrypto")
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
    except Exception as exc:  # noqa: BLE001 - 로컬에 PG 가 없으면 skip
        await engine.dispose()
        pytest.skip(f"PostgreSQL test database is not available: {exc}")
    yield engine
    await engine.dispose()


@pytest.fixture
async def db(db_engine) -> AsyncIterator[AsyncSession]:  # type: ignore[no-untyped-def]
    factory = async_sessionmaker(bind=db_engine, expire_on_commit=False, autoflush=False)
    async with factory() as session:
        yield session


@pytest.fixture
async def user(db: AsyncSession) -> User:
    row = User(login=f"tester-{uuid.uuid4().hex[:6]}", name="tester", status="active")
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


@pytest.fixture
def arq() -> FakeArq:
    return FakeArq()


@pytest.fixture(autouse=True)
def fake_redis(monkeypatch: pytest.MonkeyPatch) -> FakeRedis:
    """Redis 대역을 주입한다. `get_redis` 를 직접 import 한 모듈까지 함께 갈아끼운다."""
    redis = FakeRedis()
    for module in ("app.realtime.bus", "app.features.analysis.service"):
        monkeypatch.setattr(f"{module}.get_redis", lambda: redis)
    return redis


@pytest.fixture
async def client(db: AsyncSession, user: User, arq: FakeArq) -> AsyncIterator[AsyncClient]:
    """인증/큐 의존성을 대역으로 바꾼 API client. lifespan 은 띄우지 않는다."""
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[current_user] = lambda: user
    app.dependency_overrides[get_arq] = lambda: arq
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        yield http
    app.dependency_overrides.clear()
