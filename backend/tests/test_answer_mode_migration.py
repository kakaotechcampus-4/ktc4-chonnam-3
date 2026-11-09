"""0006 migration이 answer_mode CHECK와 기본값만 바꾸고 되돌릴 수 있는지 PostgreSQL로 검사한다."""

import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"
PREVIOUS = "0005_director_foundation_merge"
CHECK_SQL = (
    "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
    "WHERE conname = 'ck_interview_sessions_answer_mode'"
)
DEFAULT_SQL = (
    "SELECT column_default FROM information_schema.columns "
    "WHERE table_name = 'interview_sessions' AND column_name = 'answer_mode' "
    "AND table_schema = current_schema()"
)


def _migrate(connection, script, target, *, downgrade=False):
    def steps(heads, context):
        if downgrade:
            return script._downgrade_revs(target, heads)
        return script._upgrade_revs(target, heads)

    context = MigrationContext.configure(connection, opts={"fn": steps})
    with Operations.context(context):
        context.run_migrations()


async def test_answer_mode_allows_voice_and_defaults_to_voice_then_reverts():
    configured = os.environ.get("TEST_POSTGRES_URL")
    if not configured:
        pytest.skip("TEST_POSTGRES_URL is required")
    url = make_url(configured)
    if url.host not in {"localhost", "127.0.0.1", "::1"} or not (url.database or "").endswith(
        "_test"
    ):
        pytest.fail("Migration checks require a local *_test database")
    schema = "answer_mode_" + uuid4().hex
    engine = create_async_engine(
        url.set(drivername="postgresql+asyncpg"),
        poolclass=NullPool,
        connect_args={"server_settings": {"search_path": schema, "statement_timeout": "10000"}},
    )
    script = ScriptDirectory(str(MIGRATIONS))
    try:
        async with engine.begin() as db:
            await db.execute(text(f'CREATE SCHEMA "{schema}"'))
            await db.run_sync(_migrate, script, PREVIOUS)
            assert "'text'" in await db.scalar(text(CHECK_SQL))
            assert "voice" not in await db.scalar(text(CHECK_SQL))
            assert "text" in await db.scalar(text(DEFAULT_SQL))

            await db.run_sync(_migrate, script, "0006_answer_mode_voice")
            definition = await db.scalar(text(CHECK_SQL))
            assert "'text'" in definition and "'voice'" in definition
            assert "voice" in await db.scalar(text(DEFAULT_SQL))

            await db.run_sync(_migrate, script, PREVIOUS, downgrade=True)
            assert "voice" not in await db.scalar(text(CHECK_SQL))
            assert "text" in await db.scalar(text(DEFAULT_SQL))
    finally:
        async with engine.begin() as db:
            await db.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await engine.dispose()
