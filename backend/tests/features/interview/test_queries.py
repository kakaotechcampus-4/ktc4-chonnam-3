"""면접 생성 검사 쿼리. spec/backend/features/interview.md "생성 검사 해석".

docs/testing.md Interview create / task-13
"""

from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import InterviewSession
from app.features.interview import queries

from .factories import make_repo, make_run, make_user


@pytest.mark.parametrize("status", ["succeeded", "partial"])
async def test_current_run_ok(db: AsyncSession, status: str) -> None:
    user = await make_user(db)
    run = await make_run(db, user, status=status)
    assert await queries.get_current_run(db, user_id=user.id, run_id=run.id) == run


@pytest.mark.parametrize(
    "overrides",
    [
        {"status": "running"},
        {"status": "failed"},
        {"job_type": "initial_sync"},
        {"job_posting_id": None},
    ],
)
async def test_current_run_rejected(db: AsyncSession, overrides: dict[str, Any]) -> None:
    user = await make_user(db)
    run = await make_run(db, user, **overrides)
    assert await queries.get_current_run(db, user_id=user.id, run_id=run.id) is None


async def test_current_run_other_user(db: AsyncSession) -> None:
    run = await make_run(db, await make_user(db))
    other = await make_user(db)
    assert await queries.get_current_run(db, user_id=other.id, run_id=run.id) is None


@pytest.mark.parametrize(
    "repo_kwargs",
    [
        {"filter_status": "excluded"},
        {"is_private": True},
        {"is_accessible": False},
        {"l1_status": None},
        {"l1_status": "partial"},
        {"level": "l2"},
        {"in_run": False},
    ],
)
async def test_selectable_filters_out(db: AsyncSession, repo_kwargs: dict[str, Any]) -> None:
    run = await make_run(db, await make_user(db))
    ok = await make_repo(db, run)
    bad = await make_repo(db, run, **repo_kwargs)
    selectable = await queries.select_selectable_repository_ids(
        db, run_id=run.id, repository_ids=[ok.id, bad.id]
    )
    assert selectable == {ok.id}


async def test_selectable_other_run_candidate(db: AsyncSession) -> None:
    user = await make_user(db)
    run, other_run = await make_run(db, user), await make_run(db, user)
    repo = await make_repo(db, other_run)
    assert (
        await queries.select_selectable_repository_ids(db, run_id=run.id, repository_ids=[repo.id])
        == set()
    )


@pytest.mark.parametrize(
    ("status", "expected"),
    [("preparing", True), ("in_progress", True), ("completed", False), ("abandoned", False)],
)
async def test_has_active_interview(db: AsyncSession, status: str, expected: bool) -> None:
    run = await make_run(db, await make_user(db))
    assert await queries.has_active_interview(db, run_id=run.id) is False
    db.add(
        InterviewSession(
            user_id=run.user_id,
            analysis_job_id=run.id,
            job_posting_id=run.job_posting_id,
            status=status,
        )
    )
    await db.flush()
    assert await queries.has_active_interview(db, run_id=run.id) is expected
