"""record_event 검증. 실제 PostgreSQL 이 필요한 테스트는 TEST_POSTGRES_URL 이 없으면 skip 한다."""

import os
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from structlog.testing import capture_logs

import app.db.models  # noqa: F401  (FK 대상 모델 등록)
from app.db.base import Base
from app.db.models.metric import EVENT_NAMES, Event
from app.shared.events import record_event


@pytest.fixture
async def session_factory():
    database_url = os.environ.get("TEST_POSTGRES_URL")
    if not database_url:
        pytest.skip("TEST_POSTGRES_URL is required for real PostgreSQL tests")
    url = make_url(database_url)
    if url.drivername not in {"postgresql", "postgresql+asyncpg"}:
        pytest.fail("TEST_POSTGRES_URL must use PostgreSQL with asyncpg")
    schema = f"test_events_{uuid4().hex}"
    engine = create_async_engine(
        url.set(drivername="postgresql+asyncpg"),
        poolclass=NullPool,
        connect_args={"server_settings": {"search_path": schema}},
    )
    created = False
    try:
        async with engine.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            await connection.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
            await connection.run_sync(Base.metadata.create_all)
        created = True
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        try:
            if created:
                async with engine.begin() as connection:
                    await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        finally:
            await engine.dispose()


async def test_unknown_event_name_raises_before_touching_db():
    with pytest.raises(ValueError):
        await record_event(None, "not_an_event")  # type: ignore[arg-type]


async def test_records_event_with_payload(session_factory):
    async with session_factory() as db:
        await record_event(db, "report_viewed", payload={"depth": 2})
        await db.commit()
        row = (await db.execute(select(Event))).scalar_one()
        assert row.event_name == "report_viewed"
        assert row.payload == {"depth": 2}


@pytest.mark.parametrize("event_name", EVENT_NAMES)
async def test_every_defined_event_name_is_accepted(session_factory, event_name):
    async with session_factory() as db:
        await record_event(db, event_name)
        await db.commit()
        names = (await db.execute(select(Event.event_name))).scalars().all()
        assert names == [event_name]


async def test_insert_failure_keeps_outer_transaction_and_logs_once(session_factory):
    async with session_factory() as db:
        with capture_logs() as logs:
            await record_event(db, "turn_asked")
            await record_event(db, "turn_answered", user_id=uuid4())  # 존재하지 않는 FK
            await record_event(db, "report_viewed")
        await db.commit()
        count = (await db.execute(select(func.count()).select_from(Event))).scalar_one()
        assert count == 2
    failures = [log for log in logs if log["event"] == "event_record_failed"]
    assert len(failures) == 1
    assert failures[0]["event_name"] == "turn_answered"
