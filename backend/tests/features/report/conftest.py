"""리포트 라우터 테스트 공용 fixture. task-16"""

from unittest.mock import AsyncMock

import pytest

from ..interview.factories import make_interview, make_repo, make_run, make_turn, make_user
from .factories import seed_criteria


@pytest.fixture
async def enqueue(app, monkeypatch):
    mock = AsyncMock()
    monkeypatch.setattr(app.state.redis, "enqueue_job", mock)
    return mock


@pytest.fixture
async def ctx(app, db, client):
    """로그인한 사용자의 완료 면접(답변 완료 턴 1개). 리포트는 아직 없다."""
    user = await make_user(db)
    run = await make_run(db, user)
    repo = await make_repo(db, run)
    interview = await make_interview(db, run, [repo], status="completed")
    await make_turn(db, interview, 1, answered=True, persona="tech_lead")
    await seed_criteria(db)
    await db.commit()
    client.cookies.set("devon_session", await app.state.sessions.create(user.id))
    return interview, repo
