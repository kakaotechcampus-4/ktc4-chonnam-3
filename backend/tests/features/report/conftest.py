"""리포트 라우터 테스트 공용 fixture. task-16"""

from unittest.mock import AsyncMock

import pytest

from app.db.models import PromptVersion

from ..interview.factories import make_interview, make_repo, make_run, make_turn, make_user
from .factories import seed_criteria


@pytest.fixture
async def enqueue(app, monkeypatch):
    mock = AsyncMock()
    monkeypatch.setattr(app.state.redis, "enqueue_job", mock)
    return mock


@pytest.fixture
async def ctx(app, db, client):
    """로그인한 사용자의 완료 면접(tech_lead·domain_lead 답변 턴 각 1개). 리포트는 아직 없다."""
    user = await make_user(db)
    run = await make_run(db, user)
    repo = await make_repo(db, run)
    interview = await make_interview(db, run, [repo], status="completed")
    await make_turn(db, interview, 1, answered=True, persona="tech_lead")
    await make_turn(db, interview, 2, answered=True, persona="domain_lead")
    await seed_criteria(db)
    await db.commit()
    client.cookies.set("devon_session", await app.state.sessions.create(user.id))
    return interview, repo


@pytest.fixture
async def prompt(db):
    """서술(report)과 점수 판정(report_score) 두 task 의 활성 prompt."""
    db.add_all(
        PromptVersion(
            task_name=task,
            version=version,
            model=f"{task}-model",
            template="t",
            is_active=True,
        )
        for task, version in (("report", "report_v1"), ("report_score", "report_score_v1"))
    )
    await db.commit()
