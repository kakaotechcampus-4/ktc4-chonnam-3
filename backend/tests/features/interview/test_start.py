"""[면접 시작하기] 클릭이 제한 시간 타이머를 시작한다 (#259)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import InterviewTurn
from app.features.interview.turn_service import save_answer

from .factories import make_interview, make_repo, make_run, make_turn, make_user


@pytest.fixture
async def waiting(app, client, db, redis):
    """준비가 끝나 첫 질문이 있고, 아직 시작을 누르지 않은 면접."""
    run = await make_run(db, await make_user(db))
    repo = await make_repo(db, run)
    interview = await make_interview(db, run, [repo], current_turn=1, started_at=None)
    await make_turn(db, interview, 1, asked_at=datetime.now(UTC) - timedelta(minutes=5))
    await db.commit()
    client.cookies.set("devon_session", await app.state.sessions.create(run.user_id))
    return interview


async def test_waiting_interview_keeps_full_time_until_start_is_clicked(client, db, waiting):
    total = get_settings().interview_duration_seconds
    before = await client.get(f"/api/interviews/{waiting.id}")
    assert before.json()["status"] == "in_progress"
    assert before.json()["remainingSeconds"] == total

    started = await client.post(f"/api/interviews/{waiting.id}/start")
    assert started.status_code == 204
    await db.refresh(waiting)
    first = waiting.started_at
    assert first is not None
    after = await client.get(f"/api/interviews/{waiting.id}")
    assert total - 5 <= after.json()["remainingSeconds"] <= total

    # 재클릭·재시도는 처음 시각을 유지한다.
    assert (await client.post(f"/api/interviews/{waiting.id}/start")).status_code == 204
    await db.refresh(waiting)
    assert waiting.started_at == first


@pytest.mark.parametrize("status", ["preparing", "preparing_failed", "completed", "abandoned"])
async def test_start_refused_unless_in_progress(client, db, waiting, status):
    waiting.status = status
    await db.commit()
    response = await client.post(f"/api/interviews/{waiting.id}/start")
    assert response.status_code == 409 and response.json()["error"]["reason"] == "not_ready"
    await db.refresh(waiting)
    assert waiting.status == status and waiting.started_at is None


async def test_start_unknown_foreign_and_anonymous(client, db, waiting):
    assert (await client.post("/api/interviews/not-a-uuid/start")).status_code == 404
    assert (await client.post(f"/api/interviews/{uuid.uuid4()}/start")).status_code == 404
    waiting.user_id = (await make_user(db)).id
    await db.commit()
    assert (await client.post(f"/api/interviews/{waiting.id}/start")).status_code == 404
    client.cookies.clear()
    assert (await client.post(f"/api/interviews/{waiting.id}/start")).status_code == 401


async def test_answer_without_start_begins_timer_at_first_question(db, waiting):
    """시작 신호 없이 답이 와도 타이머가 영영 멈춰 있지 않다(첫 질문 시각부터 센다)."""
    assert waiting.started_at is None
    assert await save_answer(db, interview_id=waiting.id, turn_no=1, answer_text="답") is None
    await db.refresh(waiting)
    assert waiting.started_at is not None
    assert datetime.now(UTC) - waiting.started_at >= timedelta(minutes=4)


async def test_long_wait_then_first_answer_expires_at_next_question(client, db, waiting):
    """보정은 안전장치다. 클릭 없이 제한 시간보다 오래 기다린 뒤 답하면 다음 질문이 오는 순간
    이미 시간이 다 지나 있어 다음 조회에서 만료된다. 시작 기록은 FE가 보장해야 한다(#259)."""
    total = get_settings().interview_duration_seconds
    first = await db.scalar(
        select(InterviewTurn).where(InterviewTurn.interview_session_id == waiting.id)
    )
    first.asked_at = datetime.now(UTC) - timedelta(seconds=total + 60)
    await db.commit()

    assert await save_answer(db, interview_id=waiting.id, turn_no=1, answer_text="답") is None
    await db.refresh(waiting)
    waiting.current_turn = 2
    await make_turn(db, waiting, 2)
    await db.commit()

    response = await client.get(f"/api/interviews/{waiting.id}")
    assert response.json()["status"] == "completed"
    assert response.json()["remainingSeconds"] == 0


async def test_answer_after_start_keeps_clicked_time(client, db, waiting):
    await client.post(f"/api/interviews/{waiting.id}/start")
    await db.refresh(waiting)
    clicked = waiting.started_at
    assert await save_answer(db, interview_id=waiting.id, turn_no=1, answer_text="답") is None
    await db.refresh(waiting)
    assert waiting.started_at == clicked
