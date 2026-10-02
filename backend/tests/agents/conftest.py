"""Task14 DB 검증은 명시한 로컬 테스트 DB의 임시 schema만 사용한다."""

import os
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.db.base import Base
from app.db.models import (
    AnalysisJob,
    InterviewSession,
    JobPosting,
    PromptVersion,
    RepoAnalysis,
    Repository,
    SessionRepository,
    User,
)


@pytest.fixture
async def agent_sessions():
    configured = os.environ.get("TEST_POSTGRES_URL")
    if not configured:
        pytest.skip("TEST_POSTGRES_URL is required for PostgreSQL storage checks")
    url = make_url(configured)
    if url.host not in {"localhost", "127.0.0.1", "::1"} or not (url.database or "").endswith(
        "_test"
    ):
        pytest.fail("Task14 requires an explicit local *_test database")
    schema = "task14_" + uuid4().hex
    engine = create_async_engine(
        url.set(drivername="postgresql+asyncpg"),
        poolclass=NullPool,
        connect_args={"server_settings": {"search_path": schema, "statement_timeout": "10000"}},
    )
    try:
        async with engine.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            await connection.run_sync(Base.metadata.create_all)
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        async with engine.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await engine.dispose()


@pytest.fixture
async def agent_seed(agent_sessions):
    owner, other, posting_id, run_id, interview_id, repo_id = (uuid4() for _ in range(6))
    sha = "a" * 40
    async with agent_sessions.begin() as db:
        db.add_all([User(id=owner, name="owner"), User(id=other, name="other")])
        await db.flush()
        db.add(
            JobPosting(
                id=posting_id,
                normalized_url="https://www.wanted.co.kr/wd/123",
                raw_url="https://www.wanted.co.kr/wd/123",
                parse_status="succeeded",
            )
        )
        await db.flush()
        db.add(
            AnalysisJob(
                id=run_id,
                user_id=owner,
                job_type="analysis_run",
                status="succeeded",
                job_posting_id=posting_id,
            )
        )
        db.add(
            Repository(
                id=repo_id,
                user_id=owner,
                github_repo_id=123,
                name="sample",
                full_name="owner/sample",
                head_sha=sha,
            )
        )
        await db.flush()
        db.add(
            InterviewSession(
                id=interview_id,
                user_id=owner,
                analysis_job_id=run_id,
                job_posting_id=posting_id,
                status="in_progress",
            )
        )
        await db.flush()
        db.add(
            SessionRepository(
                interview_session_id=interview_id,
                repository_id=repo_id,
                snapshot_head_sha=sha,
                is_primary=True,
            )
        )
        for level in ("l1", "l2"):
            db.add(
                RepoAnalysis(
                    repository_id=repo_id,
                    analysis_level=level,
                    head_sha=sha,
                    prompt_version="fixture",
                    model="fixture",
                    status="succeeded",
                    notable_areas=[{"path": "src/main.py", "reason": "fixture"}],
                )
            )
        db.add(
            PromptVersion(
                task_name="director",
                version="director_v1",
                model="db-model",
                template="질문 생성 fixture",
                is_active=True,
            )
        )
    return dict(owner=owner, other=other, interview_id=interview_id, repo_id=repo_id, sha=sha)
