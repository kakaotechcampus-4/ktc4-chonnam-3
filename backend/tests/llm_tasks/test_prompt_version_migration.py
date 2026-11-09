"""실제 PostgreSQL의 기존 20자 컬럼을 확장하며 긴 식별자의 축약·삭제를 막는다."""

import importlib
import importlib.util
import os
from uuid import uuid4

import pytest
import pytest_asyncio
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import delete, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.db.models.knowledge import PromptVersion
from app.llm_tasks.prompt_loader import PromptSpec
from scripts.seed_prompt_versions import register_prompt_versions

MODULE = "migrations.versions.0013_prompt_version_capacity"


@pytest_asyncio.fixture
async def legacy_registry():
    value = os.environ.get("TEST_POSTGRES_URL")
    if not value:
        pytest.skip("TEST_POSTGRES_URL is required for isolated migration tests")
    url = make_url(value)
    if (
        url.drivername != "postgresql+asyncpg"
        or url.host not in {"127.0.0.1", "localhost"}
        or not (url.database or "").endswith("_test")
    ):
        pytest.fail("Migration test requires an explicit local PostgreSQL *_test database")
    schema = "test_prompt_capacity_" + uuid4().hex
    engine = create_async_engine(
        url,
        poolclass=NullPool,
        connect_args={"server_settings": {"search_path": schema, "statement_timeout": "15000"}},
    )
    try:
        async with engine.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            await connection.run_sync(PromptVersion.__table__.create)
            # 새 ORM을 사용하되 실제 기존 컬럼의 typmod를 복원해 upgrade를 검증한다.
            await connection.execute(
                text("ALTER TABLE prompt_versions ALTER COLUMN version TYPE VARCHAR(20)")
            )
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        async with engine.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await engine.dispose()


async def rows(sessions):
    async with sessions() as db:
        result = await db.execute(
            select(
                PromptVersion.task_name,
                PromptVersion.version,
                PromptVersion.model,
                PromptVersion.template,
                PromptVersion.is_active,
            ).order_by(PromptVersion.version)
        )
        return result.all()


@pytest.mark.parametrize("long_active", [True, False])
async def test_upgrade_preserves_rows_and_unsafe_downgrade_preserves_long_versions(
    legacy_registry, monkeypatch, long_active
):
    assert importlib.util.find_spec(MODULE) is not None, "Prompt version migration is missing"
    migration = importlib.import_module(MODULE)
    assert migration.down_revision == "0012_profile_refresh_outbox"
    sessions = legacy_registry
    old = PromptSpec("director", "director_v4", "old-model", "이전 본문")
    async with sessions.begin() as db:
        await register_prompt_versions(db, [old])
    original = await rows(sessions)
    engine = sessions.kw["bind"]

    def upgrade(connection):
        monkeypatch.setattr(migration, "op", Operations(MigrationContext.configure(connection)))
        migration.upgrade()
        column = next(
            x for x in inspect(connection).get_columns("prompt_versions") if x["name"] == "version"
        )
        assert column["type"].length == 100

    async with engine.begin() as connection:
        await connection.run_sync(upgrade)
    assert await rows(sessions) == original
    long = PromptSpec("director", "director_v4@" + "deployment" * 5, "new-model", "새 본문")
    async with sessions.begin() as db:
        await register_prompt_versions(db, [long])
        if not long_active:
            await register_prompt_versions(db, [old])
    before_guard = await rows(sessions)

    def reject_shortening(connection):
        monkeypatch.setattr(migration, "op", Operations(MigrationContext.configure(connection)))
        with pytest.raises(RuntimeError, match="versions must be preserved"):
            migration.downgrade()
        column = next(
            x for x in inspect(connection).get_columns("prompt_versions") if x["name"] == "version"
        )
        assert column["type"].length == 100

    async with engine.begin() as connection:
        await connection.run_sync(reject_shortening)
    assert await rows(sessions) == before_guard
    # 시험에서 만든 긴 행만 제거한다. 운영 downgrade는 자동 삭제·축약하지 않는다.
    async with sessions.begin() as db:
        await db.execute(delete(PromptVersion).where(PromptVersion.version == long.version))
    before_safe_downgrade = await rows(sessions)

    def safe_roundtrip(connection):
        monkeypatch.setattr(migration, "op", Operations(MigrationContext.configure(connection)))
        migration.downgrade()
        column = next(
            x for x in inspect(connection).get_columns("prompt_versions") if x["name"] == "version"
        )
        assert column["type"].length == 20
        migration.upgrade()

    async with engine.begin() as connection:
        await connection.run_sync(safe_roundtrip)
    assert await rows(sessions) == before_safe_downgrade
