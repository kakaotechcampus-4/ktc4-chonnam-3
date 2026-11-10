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

MIGRATIONS = Path(__file__).resolve().parents[2] / "migrations"
FOUNDATION_REVISION = "0005_director_foundation_merge"
VOICE_REVISION = "0006_answer_mode_voice"
AI_REVISION = "0014_official_source_snapshots"
COMBINED_REVISION = "0015_voice_ai_merge"
VOICE_CHECK_SQL = (
    "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
    "WHERE conname = 'ck_interview_sessions_answer_mode' "
    "AND conrelid = 'interview_sessions'::regclass"
)
ANSWER_DEFAULT_SQL = (
    "SELECT column_default FROM information_schema.columns "
    "WHERE table_schema = current_schema() AND table_name = 'interview_sessions' "
    "AND column_name = 'answer_mode'"
)


def migrate(
    connection, script, target, *, downgrade=False, split_merge=False, downgrade_target=None
):
    def steps(heads, context):
        if downgrade:
            if downgrade_target is not None:
                return script._downgrade_revs(downgrade_target, heads)
            assert len(heads) == 1
            # 신규 AI revision을 먼저 되돌린 뒤 기존 합류 revision 자체를 검사한다.
            if not split_merge and heads[0] != FOUNDATION_REVISION:
                return script._downgrade_revs(FOUNDATION_REVISION, heads)
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
    script = ScriptDirectory(str(MIGRATIONS))
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
            assert script.get_revision(FOUNDATION_REVISION).is_merge_point
            assert await db.scalar(text("SELECT to_regclass('llm_call_records')")) is not None
            await db.execute(
                text(
                    "INSERT INTO job_postings(normalized_url,raw_url,parse_status) "
                    "VALUES ('legacy-url','new-version','succeeded')"
                )
            )
            assert await db.run_sync(migrate, script, "head", downgrade=True) == (
                FOUNDATION_REVISION,
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


def test_voice_and_ai_histories_join_without_reparenting_published_revisions():
    script = ScriptDirectory(str(MIGRATIONS))
    assert len(script.get_heads()) == 1
    assert script.get_current_head() is not None
    assert set(script.get_revision(COMBINED_REVISION).down_revision) == {
        VOICE_REVISION,
        AI_REVISION,
    }
    assert script.get_revision(VOICE_REVISION).down_revision == FOUNDATION_REVISION
    assert script.get_revision("0007_ai_source_provenance").down_revision == FOUNDATION_REVISION


@pytest.mark.parametrize("applied", [VOICE_REVISION, AI_REVISION])
async def test_voice_or_ai_branch_keeps_data_and_schema_through_merge_round_trip(applied):
    configured = os.environ.get("TEST_POSTGRES_URL")
    if not configured:
        pytest.skip("TEST_POSTGRES_URL is required")
    url = make_url(configured)
    if url.host not in {"localhost", "127.0.0.1", "::1"} or not (url.database or "").endswith(
        "_test"
    ):
        pytest.fail("Agent migration checks require a local *_test database")
    schema = "voice_ai_merge_" + uuid4().hex
    engine = create_async_engine(
        url.set(drivername="postgresql+asyncpg"),
        poolclass=NullPool,
        connect_args={"server_settings": {"search_path": schema, "statement_timeout": "10000"}},
    )
    script = ScriptDirectory(str(MIGRATIONS))
    latest_head = script.get_current_head()
    try:
        async with engine.begin() as db:
            await db.execute(text(f'CREATE SCHEMA "{schema}"'))
            assert await db.run_sync(migrate, script, applied) == (applied,)
            posting_id = uuid4()
            await db.execute(
                text(
                    "INSERT INTO job_postings(id,normalized_url,raw_url,parse_status) "
                    "VALUES (:id,'before-voice-ai-merge','original-source','succeeded')"
                ),
                {"id": posting_id},
            )
            assert await db.run_sync(migrate, script, "head") == (latest_head,)
            assert "voice" in await db.scalar(text(ANSWER_DEFAULT_SQL))
            definition = await db.scalar(text(VOICE_CHECK_SQL))
            assert "'text'" in definition and "'voice'" in definition
            snapshot_oid = await db.scalar(
                text("SELECT 'official_source_snapshots'::regclass::oid")
            )
            await db.run_sync(
                migrate, script, "head", downgrade=True, downgrade_target=COMBINED_REVISION
            )
            # 합류만 해제할 때 부모 스키마를 제거하거나 테이블을 다시 만들면 안 된다.
            split_heads = await db.run_sync(
                migrate, script, "head", downgrade=True, split_merge=True
            )
            assert set(split_heads) == {VOICE_REVISION, AI_REVISION}
            assert await db.scalar(text("SELECT 'official_source_snapshots'::regclass::oid")) == (
                snapshot_oid
            )
            assert "voice" in await db.scalar(text(ANSWER_DEFAULT_SQL))
            assert await db.run_sync(migrate, script, "head") == (latest_head,)
            # 보호 대상 원문·음성 세션이 없는 경우 두 부모의 DDL도 실제로 왕복한다.
            assert await db.run_sync(migrate, script, "head", downgrade=True) == (
                FOUNDATION_REVISION,
            )
            assert "voice" not in await db.scalar(text(VOICE_CHECK_SQL))
            assert "text" in await db.scalar(text(ANSWER_DEFAULT_SQL))
            assert await db.scalar(text("SELECT to_regclass('official_source_snapshots')")) is None
            assert await db.run_sync(migrate, script, "head") == (latest_head,)
            assert "voice" in await db.scalar(text(ANSWER_DEFAULT_SQL))
            assert (
                await db.scalar(
                    text("SELECT raw_url FROM job_postings WHERE id=:id"), {"id": posting_id}
                )
                == "original-source"
            )
    finally:
        async with engine.begin() as db:
            await db.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await engine.dispose()
