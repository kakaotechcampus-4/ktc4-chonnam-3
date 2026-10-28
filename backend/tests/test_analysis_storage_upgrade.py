"""실제 DB의 두 선행 적용 순서에서 기존 자료를 지키며 최종 head로 전진한다."""

from pathlib import Path
from uuid import uuid4

import pytest
from alembic.config import Config
from alembic.runtime.environment import EnvironmentContext
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"


@pytest.mark.parametrize("first", ["0003_agent_storage_merge", "0003_analysis_runs"])
async def test_preapplied_branch_preserves_posting_job_and_call_records(test_database_url, first):
    schema = "analysis_upgrade_" + uuid4().hex
    engine = create_async_engine(
        test_database_url,
        poolclass=NullPool,
        connect_args={"server_settings": {"search_path": schema}},
    )
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS))
    script = ScriptDirectory.from_config(config)

    def advance(connection, target):
        # Alembic이 실제 graph 순서와 version 행 갱신을 모두 수행한다.
        def revisions(heads, context):
            return script._upgrade_revs(target, heads)

        with EnvironmentContext(config, script, fn=revisions) as environment:
            environment.configure(connection=connection)
            with environment.begin_transaction():
                environment.run_migrations()

    try:
        async with engine.begin() as db:
            await db.execute(text(f'CREATE SCHEMA "{schema}"'))
            await db.run_sync(advance, "0001_initial")
            user, posting, job, session, call = [uuid4() for _ in range(5)]
            await db.execute(
                text("INSERT INTO users(id,name) VALUES (:id,'Analysis merge fixture')"),
                {"id": user},
            )
            await db.execute(
                text(
                    "INSERT INTO job_postings(id,normalized_url,raw_url,parse_status) "
                    "VALUES (:id,'legacy-url','legacy-source','succeeded')"
                ),
                {"id": posting},
            )
            await db.execute(
                text(
                    "INSERT INTO analysis_jobs(id,user_id,job_type,status,fingerprint) "
                    "VALUES (:id,:user,'analysis_run','succeeded','legacy-fingerprint')"
                ),
                {"id": job, "user": user},
            )
            await db.execute(
                text(
                    "INSERT INTO interview_sessions(id,user_id,analysis_job_id,job_posting_id) "
                    "VALUES (:id,:user,:job,:posting)"
                ),
                {"id": session, "user": user, "job": job, "posting": posting},
            )
            await db.run_sync(advance, first)
            assert await db.scalar(text("SELECT version_num FROM alembic_version")) == first
            if first == "0003_agent_storage_merge":
                await db.execute(
                    text(
                        "INSERT INTO llm_call_records(id,interview_session_id,task_name,attempts) "
                        "VALUES (:id,:session,'director','[{\"model\":\"fixture-model\"}]')"
                    ),
                    {"id": call, "session": session},
                )

            await db.run_sync(advance, "head")
            versions = set(await db.scalars(text("SELECT version_num FROM alembic_version")))
            assert len(versions) == 1 and versions == set(script.get_heads())
            assert "0004_analysis_storage_merge" in {
                revision.revision for revision in script.walk_revisions()
            }
            assert (
                await db.scalar(
                    text("SELECT raw_url FROM job_postings WHERE id=:id"), {"id": posting}
                )
                == "legacy-source"
            )
            saved = (
                await db.execute(
                    text("SELECT status,fingerprint FROM analysis_jobs WHERE id=:id"),
                    {"id": job},
                )
            ).one()
            assert tuple(saved) == ("succeeded", "legacy-fingerprint")
            assert await db.scalar(text("SELECT to_regclass('llm_call_records')")) is not None
            if first == "0003_agent_storage_merge":
                assert (
                    await db.scalar(
                        text("SELECT attempts->0->>'model' FROM llm_call_records WHERE id=:id"),
                        {"id": call},
                    )
                    == "fixture-model"
                )
            await db.execute(
                text(
                    "INSERT INTO job_postings(normalized_url,raw_url,parse_status) "
                    "VALUES ('legacy-url','new-source','succeeded')"
                )
            )
            assert await db.scalar(text("SELECT count(*) FROM job_postings")) == 2
    finally:
        async with engine.begin() as db:
            await db.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await engine.dispose()
