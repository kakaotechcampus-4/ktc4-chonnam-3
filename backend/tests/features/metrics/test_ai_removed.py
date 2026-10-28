"""selection_source='ai_removed' repo 목록 쿼리.

task-17
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import SessionRepository
from app.features.metrics import queries
from tests.features.interview.factories import make_interview, make_repo, make_run, make_user


async def _sources(db: AsyncSession, sources: list[str | None]):
    run = await make_run(db, await make_user(db))
    repos = [await make_repo(db, run) for _ in sources]
    interview = await make_interview(db, run, repos)
    rows = await _rows(db, interview.id)
    for row, source in zip(sorted(rows, key=lambda r: r.display_order or 0), sources, strict=True):
        row.selection_source = source
    await db.flush()
    return interview, repos


async def _rows(db: AsyncSession, interview_id):
    result = await db.scalars(
        select(SessionRepository).where(SessionRepository.interview_session_id == interview_id)
    )
    return list(result)


async def test_lists_only_ai_removed(db: AsyncSession) -> None:
    interview, repos = await _sources(db, ["ai_removed", "user_added", None, "ai_removed"])

    result = await queries.list_ai_removed_repositories(db)

    assert {r.repository_id for r in result} == {repos[0].id, repos[3].id}
    assert {r.full_name for r in result} == {repos[0].full_name, repos[3].full_name}
    assert all(r.interview_session_id == interview.id for r in result)


async def test_empty_when_none(db: AsyncSession) -> None:
    await _sources(db, ["user_added", None])
    assert await queries.list_ai_removed_repositories(db) == []


async def test_period_filter(db: AsyncSession) -> None:
    interview, repos = await _sources(db, ["ai_removed", "ai_removed"])
    now = datetime.now(UTC)
    old = (await _rows(db, interview.id))[0]
    old.created_at = now - timedelta(days=10)
    await db.flush()

    since = now - timedelta(days=1)
    recent = await queries.list_ai_removed_repositories(db, since=since)
    earlier = await queries.list_ai_removed_repositories(db, until=since)

    assert len(recent) == 1 and len(earlier) == 1
    assert recent[0].repository_id != earlier[0].repository_id


async def test_period_boundary(db: AsyncSession) -> None:
    interview, _ = await _sources(db, ["ai_removed"])
    boundary = datetime.now(UTC) - timedelta(days=1)
    (row,) = await _rows(db, interview.id)
    row.created_at = boundary
    await db.flush()

    # since 는 포함, until 은 미포함
    assert len(await queries.list_ai_removed_repositories(db, since=boundary)) == 1
    assert await queries.list_ai_removed_repositories(db, until=boundary) == []
