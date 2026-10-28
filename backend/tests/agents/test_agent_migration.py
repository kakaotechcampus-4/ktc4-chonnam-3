"""실제 PostgreSQL에서 기존 자료를 보존하며 Task14 revision을 왕복한다."""

import importlib.util
import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool


def migration(name):
    path = Path(__file__).resolve().parents[2] / "migrations/versions" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def test_upgrade_preserves_legacy_unknown_values_and_downgrade_keeps_existing_rows():
    configured = os.environ.get("TEST_POSTGRES_URL")
    if not configured:
        pytest.skip("TEST_POSTGRES_URL is required")
    url = make_url(configured)
    if url.host not in {"localhost", "127.0.0.1", "::1"} or not (url.database or "").endswith(
        "_test"
    ):
        pytest.fail("Task14 migrations require a local *_test database")
    schema = "task14_migration_" + uuid4().hex
    engine = create_async_engine(
        url.set(drivername="postgresql+asyncpg"),
        poolclass=NullPool,
        connect_args={"server_settings": {"search_path": schema, "statement_timeout": "10000"}},
    )
    initial, added = migration("0001_initial"), migration("0002_agent_storage")
    assert added.down_revision == initial.revision

    def run(connection, operation):
        with Operations.context(MigrationContext.configure(connection)):
            operation()

    try:
        async with engine.begin() as db:
            await db.execute(text(f'CREATE SCHEMA "{schema}"'))
            await db.run_sync(run, initial.upgrade)
            owner, posting, job, repo, interview = (uuid4() for _ in range(5))
            params = dict(owner=owner, posting=posting, job=job, repo=repo, interview=interview)
            statements = [
                "INSERT INTO users(id,name) VALUES (:owner,'legacy')",
                "INSERT INTO job_postings(id,normalized_url,raw_url,parse_status) "
                "VALUES (:posting,'url','url','succeeded')",
                "INSERT INTO analysis_jobs(id,user_id,job_type) "
                "VALUES (:job,:owner,'analysis_run')",
                "INSERT INTO repositories(id,user_id,github_repo_id,name,full_name,head_sha) "
                "VALUES (:repo,:owner,1,'repo','owner/repo',repeat('a',40))",
                "INSERT INTO interview_sessions(id,user_id,analysis_job_id,job_posting_id) "
                "VALUES (:interview,:owner,:job,:posting)",
                "INSERT INTO session_repositories(interview_session_id,repository_id) "
                "VALUES (:interview,:repo)",
                "INSERT INTO interview_turns(interview_session_id,turn_no,persona,question_text) "
                "VALUES (:interview,1,'hr_manager','기존 질문')",
                "INSERT INTO evidences"
                "(interview_session_id,repository_id,source_type,git_ref,snippet) "
                "VALUES (:interview,:repo,'repo_metadata',repeat('a',40),'기존 자료')",
            ]
            for statement in statements:
                await db.execute(text(statement), params)
            await db.run_sync(run, added.upgrade)
            assert (
                await db.scalar(text("SELECT snapshot_head_sha FROM session_repositories")) is None
            )
            assert await db.scalar(text("SELECT question_contract FROM interview_turns")) is None
            assert await db.scalar(text("SELECT metadata_key FROM evidences")) is None
            await db.execute(
                text(
                    "INSERT INTO llm_call_records(interview_session_id,task_name) "
                    "VALUES (:interview,'director')"
                ),
                params,
            )
            assert await db.scalar(text("SELECT attempts FROM llm_call_records")) == []
            await db.run_sync(run, added.downgrade)
            assert await db.scalar(text("SELECT question_text FROM interview_turns")) == "기존 질문"
            assert await db.scalar(text("SELECT snippet FROM evidences")) == "기존 자료"
            assert await db.scalar(text("SELECT to_regclass('llm_call_records')")) is None
            await db.run_sync(run, added.upgrade)
            assert (
                await db.scalar(text("SELECT snapshot_head_sha FROM session_repositories")) is None
            )
    finally:
        async with engine.begin() as db:
            await db.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await engine.dispose()
