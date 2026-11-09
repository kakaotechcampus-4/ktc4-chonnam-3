"""이미 적용된 0007·0008의 CHECK를 데이터·식 변경 없이 모델 이름으로 정렬한다."""

import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.db.base import Base

MIGRATIONS = Path(__file__).resolve().parents[2] / "migrations"
EXPECTED = {
    "ck_interview_external_sources_content_scope",
    "ck_document_claim_comparisons_status",
    "ck_document_claim_comparisons_execution_status",
}


def migrate(connection, script, target, *, downgrade=False):
    def steps(heads, context):
        return (
            script._downgrade_revs(target, heads)
            if downgrade
            else script._upgrade_revs(target, heads)
        )

    context = MigrationContext.configure(
        connection, opts={"fn": steps, "target_metadata": Base.metadata}
    )
    with Operations.context(context):
        context.run_migrations()


async def checks(db):
    rows = await db.execute(
        text(
            "SELECT c.oid, c.conname, pg_get_constraintdef(c.oid) FROM pg_constraint c "
            "JOIN pg_class t ON t.oid=c.conrelid "
            "WHERE t.relnamespace=current_schema()::regnamespace AND c.contype='c' "
            "AND t.relname IN ('interview_external_sources','document_claim_comparisons')"
        )
    )
    return {oid: (name, expression) for oid, name, expression in rows}


@pytest.mark.parametrize("applied", ["0014_official_source_snapshots", "0015_voice_ai_merge"])
async def test_existing_constraint_names_round_trip_without_recreating_checks(applied):
    configured = os.environ.get("TEST_POSTGRES_URL")
    if not configured:
        pytest.skip("TEST_POSTGRES_URL is required")
    url = make_url(configured)
    if url.host not in {"localhost", "127.0.0.1", "::1"} or not (url.database or "").endswith(
        "_test"
    ):
        pytest.fail("Constraint migration checks require a local *_test database")
    schema = "source_check_names_" + uuid4().hex
    engine = create_async_engine(
        url.set(drivername="postgresql+asyncpg"),
        poolclass=NullPool,
        connect_args={"server_settings": {"search_path": schema, "statement_timeout": "10000"}},
    )
    script = ScriptDirectory(str(MIGRATIONS))
    try:
        async with engine.begin() as db:
            await db.execute(text(f'CREATE SCHEMA "{schema}"'))
            await db.run_sync(migrate, script, applied)
            before = await checks(db)
            assert len(before) == 3
            assert not EXPECTED.intersection(name for name, _ in before.values())
            await db.run_sync(migrate, script, "head")
            after = await checks(db)
            assert {name for name, _ in after.values()} == EXPECTED
            assert {oid: expr for oid, (_, expr) in after.items()} == {
                oid: expr for oid, (_, expr) in before.items()
            }
            await db.run_sync(migrate, script, "0015_voice_ai_merge", downgrade=True)
            assert await checks(db) == before
            await db.run_sync(migrate, script, "head")
            assert await checks(db) == after
    finally:
        async with engine.begin() as db:
            await db.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await engine.dispose()
