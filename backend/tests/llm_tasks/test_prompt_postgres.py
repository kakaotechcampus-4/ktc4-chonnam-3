"""Run only against an explicit TEST_POSTGRES_URL; each test owns one temporary schema."""

import asyncio
import os
from dataclasses import asdict, replace
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.llm_tasks.prompt_loader import (
    PromptConfigurationError,
    PromptNotFoundError,
    PromptSpec,
    load_active_prompt,
)
from scripts.seed_prompt_versions import (
    PROMPT_VERSIONS,
    PromptVersionConflictError,
    seed_prompt_versions,
)


@pytest.fixture
async def prompt_sessions():
    database_url = os.environ.get("TEST_POSTGRES_URL")
    if not database_url:
        pytest.skip("TEST_POSTGRES_URL is required for real PostgreSQL tests")
    url = make_url(database_url)
    if url.drivername not in {"postgresql", "postgresql+asyncpg"}:
        pytest.fail("TEST_POSTGRES_URL must use PostgreSQL with asyncpg")
    schema = f"test_prompts_{uuid4().hex}"
    engine = create_async_engine(
        url.set(drivername="postgresql+asyncpg"),
        poolclass=NullPool,
        connect_args={"server_settings": {"search_path": schema, "statement_timeout": "15000"}},
    )
    created = False
    try:
        async with engine.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            # Exact prompt_versions table/index DDL from DB branch commit
            # c731c5b87d8811885bf5f2edb07ec54569e1a7eb:
            # backend/migrations/versions/0001_initial.py:55-81,902-924.
            # Current branch has only DB skeletons; this does not test its full migration.
            await connection.execute(
                text(
                    """
                    CREATE TABLE prompt_versions (
                        id UUID DEFAULT gen_random_uuid() NOT NULL,
                        task_name VARCHAR(50) NOT NULL,
                        version VARCHAR(20) NOT NULL,
                        model TEXT NOT NULL,
                        template TEXT NOT NULL,
                        is_active BOOLEAN DEFAULT false NOT NULL,
                        notes TEXT,
                        created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
                        updated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
                        CONSTRAINT pk_prompt_versions PRIMARY KEY (id),
                        CONSTRAINT uq_prompt_versions_task_version UNIQUE (task_name, version)
                    )
                    """
                )
            )
            await connection.execute(
                text(
                    "CREATE UNIQUE INDEX uq_prompt_versions_active_per_task "
                    "ON prompt_versions (task_name) WHERE is_active"
                )
            )
        created = True
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        try:
            if created:
                async with engine.begin() as connection:
                    await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        finally:
            await engine.dispose()


def _prompts():
    return [
        PromptSpec(task, version, "test-model", f"검수된 테스트 본문: {task}.")
        for task, version in sorted(PROMPT_VERSIONS.items())
    ]


async def _insert(session, prompt, *, active):
    await session.execute(
        text(
            "INSERT INTO prompt_versions (task_name, version, model, template, is_active) "
            "VALUES (:task_name, :version, :model, :template, :is_active)"
        ),
        asdict(prompt) | {"is_active": active},
    )


async def _rows(sessions):
    async with sessions() as session:
        result = await session.execute(
            text("SELECT * FROM prompt_versions ORDER BY task_name, version")
        )
        return [dict(row) for row in result.mappings()]


async def test_postgres_seed_roundtrip_and_idempotence(prompt_sessions):
    prompts = _prompts()
    async with prompt_sessions.begin() as session:
        await seed_prompt_versions(session, prompts)
    before = await _rows(prompt_sessions)
    assert len(before) == 7
    assert all(row["is_active"] and row["id"] and row["created_at"] for row in before)

    async with prompt_sessions.begin() as session:
        await seed_prompt_versions(session, prompts)
        for prompt in prompts:
            assert await load_active_prompt(session, f" {prompt.task_name} ") == prompt
    # Includes UUIDs and timestamps: rerunning must not rewrite existing versions.
    assert await _rows(prompt_sessions) == before


@pytest.mark.parametrize("inactive_only", [False, True])
async def test_postgres_loader_rejects_missing_active_prompt(prompt_sessions, inactive_only):
    prompt = _prompts()[0]
    async with prompt_sessions.begin() as session:
        if inactive_only:
            await _insert(session, prompt, active=False)
        with pytest.raises(PromptNotFoundError):
            await load_active_prompt(session, prompt.task_name)


@pytest.mark.parametrize("existing_target", [False, True])
async def test_postgres_seed_replaces_old_active_version(prompt_sessions, existing_target):
    prompts = _prompts()
    target = prompts[0]
    old = replace(target, version="old_v0", model="old-model", template="Old body")
    async with prompt_sessions.begin() as session:
        await _insert(session, old, active=True)
        if existing_target:
            await _insert(session, target, active=False)
    before = await _rows(prompt_sessions)

    async with prompt_sessions.begin() as session:
        await seed_prompt_versions(session, prompts)
        assert await load_active_prompt(session, target.task_name) == target
    after = await _rows(prompt_sessions)
    assert len(after) == 8
    assert sum(row["is_active"] for row in after) == 7
    old_after = next(row for row in after if row["version"] == old.version)
    assert not old_after["is_active"]
    for original in before:
        current = next(row for row in after if row["id"] == original["id"])
        assert {k: v for k, v in current.items() if k not in {"is_active", "updated_at"}} == {
            k: v for k, v in original.items() if k not in {"is_active", "updated_at"}
        }


@pytest.mark.parametrize("field", ["template", "model"])
async def test_postgres_seed_preserves_existing_content_on_conflict(prompt_sessions, field):
    prompts = _prompts()
    async with prompt_sessions.begin() as session:
        await seed_prompt_versions(session, prompts)
    before = await _rows(prompt_sessions)
    prompts[-1] = replace(prompts[-1], **{field: "changed value"})

    with pytest.raises(PromptVersionConflictError):
        async with prompt_sessions.begin() as session:
            await seed_prompt_versions(session, prompts)
    assert await _rows(prompt_sessions) == before


async def test_postgres_seed_leaves_visibility_and_rollback_to_caller(prompt_sessions):
    prompts = _prompts()
    async with prompt_sessions.begin() as session:
        await _insert(session, replace(prompts[0], version="old_v0"), active=True)
    before = await _rows(prompt_sessions)

    with pytest.raises(RuntimeError, match="caller rollback"):
        async with prompt_sessions.begin() as session:
            await seed_prompt_versions(session, prompts)
            assert await load_active_prompt(session, prompts[0].task_name) == prompts[0]
            assert await _rows(prompt_sessions) == before
            raise RuntimeError("caller rollback")
    assert await _rows(prompt_sessions) == before


@pytest.mark.parametrize(
    ("version", "active", "constraint"),
    [
        (None, False, "uq_prompt_versions_task_version"),
        ("other_v2", True, "uq_prompt_versions_active_per_task"),
    ],
)
async def test_postgres_enforces_prompt_uniqueness(prompt_sessions, version, active, constraint):
    prompt = _prompts()[0]
    async with prompt_sessions.begin() as session:
        await _insert(session, prompt, active=True)
    before = await _rows(prompt_sessions)

    with pytest.raises(IntegrityError, match=constraint) as error:
        async with prompt_sessions.begin() as session:
            await _insert(
                session, replace(prompt, version=version or prompt.version), active=active
            )
    assert error.value.orig.sqlstate == "23505"
    assert await _rows(prompt_sessions) == before


async def test_postgres_loader_detects_multiple_active_rows_if_index_is_missing(prompt_sessions):
    prompt = _prompts()[0]
    async with prompt_sessions.begin() as session:
        await _insert(session, prompt, active=True)
    before = await _rows(prompt_sessions)

    # Simulate a damaged schema only inside a transaction that restores the index on rollback.
    with pytest.raises(PromptConfigurationError):
        async with prompt_sessions.begin() as session:
            await session.execute(text("DROP INDEX uq_prompt_versions_active_per_task"))
            await _insert(session, replace(prompt, version="other_v2"), active=True)
            await load_active_prompt(session, prompt.task_name)
    assert await _rows(prompt_sessions) == before
    async with prompt_sessions() as session:
        assert (
            await session.scalar(
                text(
                    "SELECT count(*) FROM pg_indexes WHERE schemaname = current_schema() "
                    "AND indexname = 'uq_prompt_versions_active_per_task'"
                )
            )
            == 1
        )


@pytest.mark.parametrize("conflicting", [False, True])
async def test_postgres_concurrent_seeds_wait_for_transaction_lock(prompt_sessions, conflicting):
    prompts = _prompts()
    second_prompts = list(prompts)
    if conflicting:
        second_prompts[-1] = replace(second_prompts[-1], template="Conflicting body")
    ready = asyncio.get_running_loop().create_future()

    async def second_seed():
        async with prompt_sessions.begin() as session:
            ready.set_result(await session.scalar(text("SELECT pg_backend_pid()")))
            await seed_prompt_versions(session, second_prompts)

    async with prompt_sessions.begin() as first:
        first_pid = await first.scalar(text("SELECT pg_backend_pid()"))
        await seed_prompt_versions(first, prompts)
        result = await first.execute(
            text("SELECT * FROM prompt_versions ORDER BY task_name, version")
        )
        expected = [dict(row) for row in result.mappings()]
        contender = asyncio.create_task(second_seed())
        try:
            second_pid = await asyncio.wait_for(ready, timeout=10)
            async with prompt_sessions() as observer:
                # Poll observed database state, with no timing-based sleep or success assumption.
                async with asyncio.timeout(10):
                    while not await observer.scalar(
                        text("SELECT :holder = ANY(pg_blocking_pids(:waiter))"),
                        {"holder": first_pid, "waiter": second_pid},
                    ):
                        pass
                assert await observer.scalar(text("SELECT count(*) FROM prompt_versions")) == 0
            await first.commit()
            if conflicting:
                with pytest.raises(PromptVersionConflictError):
                    await asyncio.wait_for(contender, timeout=10)
            else:
                await asyncio.wait_for(contender, timeout=10)
        finally:
            if not contender.done():
                contender.cancel()
            await asyncio.gather(contender, return_exceptions=True)

    assert len(expected) == 7
    assert all(row["is_active"] for row in expected)
    assert await _rows(prompt_sessions) == expected
