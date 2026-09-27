"""score_criteria / domain_question_frames 시드의 실제 PostgreSQL upsert·idempotent 검증.

Run only against an explicit TEST_POSTGRES_URL; each test owns one temporary schema
(tests/llm_tasks/test_prompt_postgres.py 와 같은 패턴).
"""

import os
from dataclasses import replace
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.db.models.knowledge import DomainQuestionFrame, ScoreCriterion
from scripts.seed_domain_question_frames import DOMAIN_QUESTION_FRAMES, seed_domain_question_frames
from scripts.seed_score_criteria import SCORE_CRITERIA, seed_score_criteria


@pytest.fixture
async def seed_sessions():
    database_url = os.environ.get("TEST_POSTGRES_URL")
    if not database_url:
        pytest.skip("TEST_POSTGRES_URL is required for real PostgreSQL tests")
    url = make_url(database_url)
    if url.drivername not in {"postgresql", "postgresql+asyncpg"}:
        pytest.fail("TEST_POSTGRES_URL must use PostgreSQL with asyncpg")
    schema = f"test_seed_{uuid4().hex}"
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
            await connection.run_sync(ScoreCriterion.__table__.create)
            await connection.run_sync(DomainQuestionFrame.__table__.create)
        created = True
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        try:
            if created:
                async with engine.begin() as connection:
                    await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        finally:
            await engine.dispose()


async def test_score_criteria_seed_is_idempotent(seed_sessions) -> None:
    async with seed_sessions() as session:
        await seed_score_criteria(session)
        await session.commit()
        rows_before = (
            await session.execute(text("SELECT score_key, label_ko FROM score_criteria"))
        ).all()

        await seed_score_criteria(session)
        await session.commit()
        rows_after = (
            await session.execute(text("SELECT score_key, label_ko FROM score_criteria"))
        ).all()

        assert len(rows_before) == len(SCORE_CRITERIA)
        assert sorted(rows_before) == sorted(rows_after)


async def test_score_criteria_seed_updates_changed_label(seed_sessions) -> None:
    async with seed_sessions() as session:
        await seed_score_criteria(session)
        await session.commit()

        changed = list(SCORE_CRITERIA)
        changed[0] = replace(changed[0], label_ko="수정된 라벨")
        await seed_score_criteria(session, changed)
        await session.commit()

        label = await session.scalar(
            text("SELECT label_ko FROM score_criteria WHERE score_key = :key"),
            {"key": changed[0].score_key},
        )
        assert label == "수정된 라벨"


async def test_domain_question_frames_seed_is_idempotent(seed_sessions) -> None:
    async with seed_sessions() as session:
        await seed_domain_question_frames(session)
        await session.commit()
        count_before = await session.scalar(text("SELECT count(*) FROM domain_question_frames"))

        await seed_domain_question_frames(session)
        await session.commit()
        count_after = await session.scalar(text("SELECT count(*) FROM domain_question_frames"))

        assert count_before == len(DOMAIN_QUESTION_FRAMES)
        assert count_after == count_before
