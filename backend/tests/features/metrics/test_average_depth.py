"""평균 depth 쿼리.

task-17
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.metrics import queries
from tests.features.interview.factories import (
    make_interview,
    make_repo,
    make_run,
    make_turn,
    make_user,
)


async def _interview(db: AsyncSession):
    run = await make_run(db, await make_user(db))
    return await make_interview(db, run, [await make_repo(db, run)])


async def test_average_depth_counts_every_turn(db: AsyncSession) -> None:
    interview = await _interview(db)
    await make_turn(db, interview, 1, depth=1)
    await make_turn(db, interview, 2, depth=2, answered=True)
    await make_turn(db, interview, 3, depth=3)

    assert await queries.get_average_depth(db) == pytest.approx(2.0)


async def test_average_depth_none_without_turns(db: AsyncSession) -> None:
    assert await queries.get_average_depth(db) is None


async def test_average_depth_period_filter(db: AsyncSession) -> None:
    interview = await _interview(db)
    now = datetime.now(UTC)
    old = await make_turn(db, interview, 1, depth=1)
    old.created_at = now - timedelta(days=10)
    await make_turn(db, interview, 2, depth=3)
    await db.flush()

    since = now - timedelta(days=1)
    assert await queries.get_average_depth(db, since=since) == pytest.approx(3.0)
    assert await queries.get_average_depth(db, until=since) == pytest.approx(1.0)
    assert await queries.get_average_depth(db, since=now + timedelta(days=1)) is None


async def test_average_depth_period_boundary(db: AsyncSession) -> None:
    interview = await _interview(db)
    boundary = datetime.now(UTC) - timedelta(days=1)
    turn = await make_turn(db, interview, 1, depth=2)
    turn.created_at = boundary
    await db.flush()

    # since 는 포함, until 은 미포함
    assert await queries.get_average_depth(db, since=boundary) == pytest.approx(2.0)
    assert await queries.get_average_depth(db, until=boundary) is None
