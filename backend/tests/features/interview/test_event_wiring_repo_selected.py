"""repo_selected 이벤트 연결. task-17"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.models import InterviewSession
from tests.event_helpers import broken_events as broken_events
from tests.event_helpers import fail_commit_on, names

from .factories import make_repo, make_run, make_user
from .test_service import FakeRedis, _create


async def test_repo_selected_recorded_once_per_created_interview(db: AsyncSession) -> None:
    run, repos = await _selectable(db)

    await _create(db, run, [r.id for r in repos])
    try:
        await _create(db, run, [r.id for r in repos])  # 진행 중 면접이 있어 거부된다
    except AppError:
        pass

    assert await names(db) == ["repo_selected"]


async def test_repo_selected_recorded_once_when_enqueue_fails(db: AsyncSession) -> None:
    """enqueue 실패에도 면접 행과 선택은 commit 되어 남으므로 이벤트를 1회 기록한다."""
    run, repos = await _selectable(db)

    interview_id, session_id = await _create(
        db, run, [r.id for r in repos], FakeRedis(enqueue_fail=True)
    )

    assert interview_id and session_id
    assert await names(db) == ["repo_selected"]


async def test_repo_selected_failure_does_not_block_create(db: AsyncSession, broken_events) -> None:
    run, repos = await _selectable(db)

    interview_id, session_id = await _create(db, run, [r.id for r in repos])

    assert interview_id and session_id
    assert await names(db) == []


async def test_event_commit_failure_still_returns_created_ids(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    run, repos = await _selectable(db)
    fail_commit_on(monkeypatch, nth=2)  # 1번째는 면접 본체, 2번째가 이벤트 전용 commit

    interview_id, session_id = await _create(db, run, [r.id for r in repos])

    assert interview_id and session_id
    assert (await db.get(InterviewSession, interview_id)) is not None
    assert await names(db) == []


async def _selectable(db: AsyncSession):
    run = await make_run(db, await make_user(db))
    return run, [await make_repo(db, run), await make_repo(db, run)]
