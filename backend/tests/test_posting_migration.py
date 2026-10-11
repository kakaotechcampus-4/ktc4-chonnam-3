"""공고 버전 migration은 과거 자료를 보존하고 위험한 downgrade를 거절한다."""

import asyncio
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import asyncpg
from sqlalchemy.engine import make_url

BACKEND_ROOT = Path(__file__).resolve().parents[1]


async def test_posting_migration_preserves_history_and_refuses_lossy_downgrade(test_database_url):
    name = f"task09_migration_test_{uuid4().hex}"
    url = make_url(test_database_url)
    admin = await asyncpg.connect(
        url.set(drivername="postgresql", database="postgres").render_as_string(hide_password=False)
    )
    await admin.execute(f'CREATE DATABASE "{name}"')
    database_url = url.set(database=name).render_as_string(hide_password=False)
    connection = None

    async def migrate(*args):
        return await asyncio.to_thread(
            subprocess.run,
            [sys.executable, "-m", "alembic", *args],
            cwd=BACKEND_ROOT,
            env={**os.environ, "DATABASE_URL": database_url, "PYTHONUTF8": "1"},
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

    try:
        result = await migrate("upgrade", "0001_initial")
        assert result.returncode == 0, result.stderr
        connection = await asyncpg.connect(
            url.set(drivername="postgresql", database=name).render_as_string(hide_password=False)
        )
        first, second, requirement = uuid4(), uuid4(), uuid4()
        posting_url = "https://www.wanted.co.kr/wd/123"
        await connection.execute(
            "INSERT INTO job_postings (id,normalized_url,raw_url,parse_status) "
            "VALUES ($1,$2,$2,'succeeded')",
            first,
            posting_url,
        )
        await connection.execute(
            "INSERT INTO jd_requirements (id,job_posting_id,category,text,display_order) "
            "VALUES ($1,$2,'required','Python',0)",
            requirement,
            first,
        )
        result = await migrate("upgrade", "head")
        assert result.returncode == 0, result.stderr
        # UNIQUE가 남으면 실제 두 번째 버전 INSERT가 실패한다.
        await connection.execute(
            "INSERT INTO job_postings (id,normalized_url,raw_url,parse_status) "
            "VALUES ($1,$2,$2,'succeeded')",
            second,
            posting_url,
        )
        assert (
            await connection.fetchval(
                "SELECT job_posting_id FROM jd_requirements WHERE id=$1", requirement
            )
            == first
        )
        assert await connection.fetchval("SELECT count(*) FROM job_postings") == 2
        result = await migrate("check")
        assert result.returncode == 0, result.stderr
        result = await migrate("downgrade", "0001_initial")
        assert result.returncode != 0
        assert "공고 이력" in result.stderr
        assert await connection.fetchval("SELECT count(*) FROM job_postings") == 2
        assert (
            await connection.fetchval(
                "SELECT job_posting_id FROM jd_requirements WHERE id=$1", requirement
            )
            == first
        )
        # 이 테스트가 만든 참조 없는 두 번째 자료만 제거하면 정상 rollback도 가능하다.
        await connection.execute("DELETE FROM job_postings WHERE id=$1", second)
        result = await migrate("downgrade", "0001_initial")
        assert result.returncode == 0, result.stderr
        result = await migrate("upgrade", "head")
        assert result.returncode == 0, result.stderr
        assert await connection.fetchval("SELECT count(*) FROM job_postings") == 1
    finally:
        if connection is not None:
            await connection.close()
        await admin.execute(f'DROP DATABASE "{name}"')
        await admin.close()
