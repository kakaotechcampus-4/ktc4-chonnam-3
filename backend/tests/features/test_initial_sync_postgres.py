"""initial_sync upsert 를 실제 PostgreSQL 제약(ON CONFLICT)으로 검증한다.

Run only against an explicit TEST_POSTGRES_URL; each test owns one temporary schema
(tests/llm_tasks/test_prompt_postgres.py 와 같은 패턴).
"""

import os
from unittest import mock
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.db.models.github import Repository
from app.db.models.user import User
from app.features.analysis.pipeline.initial_sync import run_initial_sync
from app.integrations.github.base import RepoSummary
from app.integrations.github.client import GithubClient


@pytest.fixture
async def sync_sessions():
    database_url = os.environ.get("TEST_POSTGRES_URL")
    if not database_url:
        pytest.skip("TEST_POSTGRES_URL is required for real PostgreSQL tests")
    url = make_url(database_url)
    if url.drivername not in {"postgresql", "postgresql+asyncpg"}:
        pytest.fail("TEST_POSTGRES_URL must use PostgreSQL with asyncpg")
    schema = f"test_initial_sync_{uuid4().hex}"
    engine = create_async_engine(
        url.set(drivername="postgresql+asyncpg"),
        poolclass=NullPool,
        connect_args={"server_settings": {"search_path": schema}},
    )
    created = False
    try:
        async with engine.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            await connection.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
            await connection.run_sync(User.__table__.create)
            await connection.run_sync(Repository.__table__.create)
        created = True
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        try:
            if created:
                async with engine.begin() as connection:
                    await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        finally:
            await engine.dispose()


def _client(*repos: RepoSummary) -> GithubClient:
    client = mock.create_autospec(GithubClient, instance=True)
    client.list_repositories = mock.AsyncMock(return_value=list(repos))
    return client


async def test_initial_sync_inserts_new_repos(sync_sessions) -> None:
    async with sync_sessions() as session:
        user = User(name="octocat")
        session.add(user)
        await session.flush()
        user_id = user.id

        repo = RepoSummary(
            github_repo_id=1,
            name="devon",
            full_name="octocat/devon",
            primary_language="Python",
            size_kb=100,
        )
        count = await run_initial_sync(
            session, user_id=user_id, github_account_id=uuid4(), client=_client(repo)
        )
        await session.commit()

        assert count == 1
        rows = (await session.execute(select(Repository))).scalars().all()
        assert len(rows) == 1
        assert rows[0].full_name == "octocat/devon"
        assert rows[0].is_accessible is True


async def test_initial_sync_is_idempotent_and_updates_changed_fields(sync_sessions) -> None:
    async with sync_sessions() as session:
        user = User(name="octocat")
        session.add(user)
        await session.flush()
        user_id = user.id
        github_account_id = uuid4()

        first = RepoSummary(
            github_repo_id=1, name="devon", full_name="octocat/devon", stars=1, size_kb=100
        )
        await run_initial_sync(
            session, user_id=user_id, github_account_id=github_account_id, client=_client(first)
        )
        await session.commit()

        updated = RepoSummary(
            github_repo_id=1, name="devon", full_name="octocat/devon", stars=42, size_kb=100
        )
        count = await run_initial_sync(
            session,
            user_id=user_id,
            github_account_id=github_account_id,
            client=_client(updated),
        )
        await session.commit()

        assert count == 1
        rows = (await session.execute(select(Repository))).scalars().all()
        assert len(rows) == 1
        assert rows[0].stars == 42
