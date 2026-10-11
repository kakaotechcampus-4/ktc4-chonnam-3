"""전용 PostgreSQL에서 분석 중복 제약과 무손실 downgrade를 검증한다."""

import asyncio
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import asyncpg
import pytest
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.features.analysis.pipeline.initial_sync import enqueue_initial_sync

BACKEND_ROOT = Path(__file__).resolve().parents[1]
BEFORE = "0002_posting_versions"
AFTER = "0003_analysis_runs"


async def test_analysis_migration_preserves_jobs_and_scopes_active_uniqueness():
    database_url = os.getenv("TASK11_MIGRATION_URL")
    if not database_url:
        pytest.skip("Set TASK11_MIGRATION_URL to the dedicated task11_migration_test database")
    url = make_url(database_url)
    # 실행 중인 API 테스트 DB나 앱 DB로 migration 검증을 돌리지 않는다.
    assert url.get_backend_name() == "postgresql"
    assert url.database == "task11_migration_test"
    assert url.host in {"127.0.0.1", "localhost"}

    async def migrate(*args):
        return await asyncio.to_thread(
            subprocess.run,
            [sys.executable, "-X", "utf8", "-m", "alembic", *args],
            cwd=BACKEND_ROOT,
            env={**os.environ, "DATABASE_URL": database_url, "PYTHONUTF8": "1"},
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

    result = await migrate("upgrade", "head")
    assert result.returncode == 0, result.stderr
    result = await migrate("downgrade", BEFORE)
    assert result.returncode == 0, result.stderr
    connection = await asyncpg.connect(
        url.set(drivername="postgresql").render_as_string(hide_password=False)
    )
    user_ids = [uuid4(), uuid4()]
    engine = create_async_engine(database_url, poolclass=NullPool)

    async def insert_job(user_id, fingerprint, *, status="queued", job_type="analysis_run"):
        return await connection.fetchval(
            "INSERT INTO analysis_jobs (user_id,job_type,status,fingerprint) "
            "VALUES ($1,$2,$3,$4) RETURNING id",
            user_id,
            job_type,
            status,
            fingerprint,
        )

    async def jobs():
        return await connection.fetch(
            "SELECT id,user_id,job_type,status,fingerprint FROM analysis_jobs "
            "WHERE user_id=ANY($1::uuid[]) ORDER BY id",
            user_ids,
        )

    try:
        await connection.executemany(
            "INSERT INTO users (id,name) VALUES ($1,'Task11 migration fixture')",
            [(user_id,) for user_id in user_ids],
        )
        legacy = await insert_job(user_ids[0], None)
        other_legacy = await insert_job(user_ids[1], None)
        with pytest.raises(asyncpg.UniqueViolationError):
            await insert_job(user_ids[0], "before-upgrade")

        result = await migrate("upgrade", AFTER)
        assert result.returncode == 0, result.stderr
        assert {row["id"] for row in await jobs()} == {legacy, other_legacy}
        assert all(row["fingerprint"] is None for row in await jobs())
        first = await insert_job(user_ids[0], "input-a")
        await insert_job(user_ids[0], "input-b")
        await insert_job(user_ids[1], "input-a")
        for fingerprint in ("input-a", None):
            with pytest.raises(asyncpg.UniqueViolationError):
                await insert_job(user_ids[0], fingerprint)

        # 모든 종료 상태는 같은 fingerprint의 신규 active 작업을 막지 않는다.
        for status in ("succeeded", "partial", "failed", "canceled"):
            await insert_job(user_ids[0], "input-a", status=status)
        await connection.execute("UPDATE analysis_jobs SET status='succeeded' WHERE id=$1", first)
        replacement = await insert_job(user_ids[0], "input-a")
        assert replacement != first

        # 기존 initial_sync 호출의 ON CONFLICT 추론도 변경된 partial index와 일치해야 한다.
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        redis = MagicMock()
        redis.enqueue_job = AsyncMock(return_value=object())
        async with sessions() as session:
            sync_id = await enqueue_initial_sync(session, redis, user_ids[0])
        async with sessions() as session:
            assert await enqueue_initial_sync(session, redis, user_ids[0]) == sync_id
        with pytest.raises(asyncpg.UniqueViolationError):
            await insert_job(user_ids[0], None, job_type="initial_sync")
        assert (
            await connection.fetchval(
                "SELECT count(*) FROM analysis_jobs WHERE user_id=$1 AND job_type='initial_sync'",
                user_ids[0],
            )
            == 1
        )

        started_at = datetime.now(UTC)
        page_id = await connection.fetchval(
            "INSERT INTO analysis_repo_candidate_pages "
            "(analysis_job_id,page_no,status,started_at,duration_ms,queue_wait_ms) "
            "VALUES ($1,2,'succeeded',$2,150,30) RETURNING id",
            legacy,
            started_at,
        )
        before = await jobs()
        result = await migrate("downgrade", BEFORE)
        assert result.returncode != 0
        assert "Finish concurrent analysis runs" in result.stderr
        assert await jobs() == before
        assert await connection.fetchval("SELECT version_num FROM alembic_version") == AFTER
        page = await connection.fetchrow(
            "SELECT started_at,duration_ms,queue_wait_ms "
            "FROM analysis_repo_candidate_pages WHERE id=$1",
            page_id,
        )
        assert tuple(page) == (started_at, 150, 30)

        # 행을 삭제하지 않고 작업을 종료하면 기존 제약으로 안전하게 되돌릴 수 있다.
        await connection.execute(
            "UPDATE analysis_jobs SET status='succeeded' "
            "WHERE user_id=ANY($1::uuid[]) AND status IN ('queued','running')",
            user_ids,
        )
        count = len(await jobs())
        result = await migrate("downgrade", BEFORE)
        assert result.returncode == 0, result.stderr
        assert len(await jobs()) == count
        assert await connection.fetchval("SELECT version_num FROM alembic_version") == BEFORE
        assert (
            await connection.fetchval(
                "SELECT count(*) FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name='analysis_repo_candidate_pages' "
                "AND column_name IN ('started_at','duration_ms','queue_wait_ms')"
            )
            == 0
        )
        await insert_job(user_ids[0], "restored-a")
        with pytest.raises(asyncpg.UniqueViolationError):
            await insert_job(user_ids[0], "restored-b")

        result = await migrate("upgrade", "head")
        assert result.returncode == 0, result.stderr
        await insert_job(user_ids[0], "restored-b")
        assert (
            await connection.fetchval(
                "SELECT count(*) FROM analysis_repo_candidate_pages WHERE id=$1", page_id
            )
            == 1
        )
        result = await migrate("check")
        assert result.returncode == 0, result.stderr
    finally:
        await engine.dispose()
        # 이 테스트가 만든 사용자와 그 소유 자료만 정리한다.
        await connection.execute("DELETE FROM users WHERE id=ANY($1::uuid[])", user_ids)
        await connection.close()
