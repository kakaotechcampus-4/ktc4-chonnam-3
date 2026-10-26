"""기적용 가지의 자료를 보존하며 실제 Alembic graph의 합류를 왕복한다."""

import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.runtime.migration import MigrationStep
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool


def migrate(connection, script, target, *, downgrade=False):
    def steps(heads, context):
        if downgrade:
            assert len(heads) == 1
            revision = script.get_revision(heads[0])
            assert revision.is_merge_point
            # 부모를 골라 DDL까지 되돌리지 않고 현재 합류 revision만 해제한다.
            return [MigrationStep.downgrade_from_script(script.revision_map, revision)]
        return script._upgrade_revs(target, heads)

    context = MigrationContext.configure(connection, opts={"fn": steps})
    with Operations.context(context):
        context.run_migrations()
    return context.get_current_heads()


@pytest.mark.parametrize("applied", ["0002_agent_storage", "0002_posting_versions"])
async def test_applied_branch_keeps_legacy_postings_through_merge_round_trip(applied):
    configured = os.environ.get("TEST_POSTGRES_URL")
    if not configured:
        pytest.skip("TEST_POSTGRES_URL is required")
    url = make_url(configured)
    if url.host not in {"localhost", "127.0.0.1", "::1"} or not (url.database or "").endswith(
        "_test"
    ):
        pytest.fail("Agent migration checks require a local *_test database")
    schema = "agent_merge_" + uuid4().hex
    engine = create_async_engine(
        url.set(drivername="postgresql+asyncpg"),
        poolclass=NullPool,
        connect_args={"server_settings": {"search_path": schema, "statement_timeout": "10000"}},
    )
    script = ScriptDirectory(str(Path(__file__).resolve().parents[2] / "migrations"))
    try:
        async with engine.begin() as db:
            await db.execute(text(f'CREATE SCHEMA "{schema}"'))
            await db.run_sync(migrate, script, "0001_initial")
            posting_id = uuid4()
            await db.execute(
                text(
                    "INSERT INTO job_postings(id,normalized_url,raw_url,parse_status) "
                    "VALUES (:id,'legacy-url','legacy-original','succeeded')"
                ),
                {"id": posting_id},
            )
            assert await db.run_sync(migrate, script, applied) == (applied,)
            heads = await db.run_sync(migrate, script, "head")
            assert len(heads) == 1 and set(heads) == set(script.get_heads())
            assert script.get_revision(heads[0]).is_merge_point
            assert await db.scalar(text("SELECT to_regclass('llm_call_records')")) is not None
            await db.execute(
                text(
                    "INSERT INTO job_postings(normalized_url,raw_url,parse_status) "
                    "VALUES ('legacy-url','new-version','succeeded')"
                )
            )
            await db.run_sync(migrate, script, "head", downgrade=True)
            assert await db.scalar(text("SELECT count(*) FROM job_postings")) == 2
            assert (
                await db.scalar(
                    text("SELECT raw_url FROM job_postings WHERE id=:id"), {"id": posting_id}
                )
                == "legacy-original"
            )
            assert await db.scalar(text("SELECT to_regclass('llm_call_records')")) is not None
            reapplied = await db.run_sync(migrate, script, "head")
            assert len(reapplied) == 1 and set(reapplied) == set(script.get_heads())
            assert await db.scalar(text("SELECT count(*) FROM job_postings")) == 2
    finally:
        async with engine.begin() as db:
            await db.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await engine.dispose()
