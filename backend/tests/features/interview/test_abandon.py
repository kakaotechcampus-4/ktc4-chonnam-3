"""명시 중단은 영구 상태를 먼저 확정하고 기존 질문·답변 기록을 보존한다."""

import asyncio
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.db.models import InterviewSession, InterviewTurn
from app.features.interview import service
from app.features.interview.turn_service import TurnRejected, save_answer, save_question

from .factories import make_interview, make_repo, make_run, make_turn, make_user


@pytest.fixture
async def current(app, client, db, redis):
    run = await make_run(db, await make_user(db))
    repo = await make_repo(db, run)
    interview = await make_interview(db, run, [repo], current_turn=2)
    await make_turn(db, interview, 1, answered=True)
    await make_turn(db, interview, 2)
    await db.commit()
    client.cookies.set("devon_session", await app.state.sessions.create(run.user_id))
    realtime = await service._issue_session_id(
        redis, interview_id=interview.id, user_id=run.user_id
    )
    return interview, realtime


async def test_abandon_204_keeps_turns_revokes_socket_and_releases_run(client, db, redis, current):
    interview, realtime = current
    await redis.set(f"ws:lock:{realtime}", "socket-owner", ex=30)
    await redis.set(f"iv:ctx:{interview.id}", "cached")
    async with redis.pubsub() as control:
        await control.subscribe(f"ws:replace:{realtime}")
        await control.get_message(timeout=1)
        response = await client.post(f"/api/interviews/{interview.id}/abandon")
        assert response.status_code == 204 and response.content == b""
        message = await control.get_message(ignore_subscribe_messages=True, timeout=1)
        assert message is not None and message["data"] == b"socket-owner"
    await db.refresh(interview)
    first_time = interview.abandoned_at
    assert interview.status == "abandoned" and first_time is not None
    assert interview.abandoned_at_turn == 2
    turns = list(await db.scalars(select(InterviewTurn).order_by(InterviewTurn.turn_no)))
    assert [(turn.status, turn.answer_text) for turn in turns] == [
        ("answered", "답변 1"),
        ("asked", None),
    ]
    assert not await redis.exists(f"rt:{realtime}", f"rt:interview:{interview.id}")
    assert not await redis.exists(f"iv:ctx:{interview.id}")
    restored = await client.get(f"/api/interviews/{interview.id}")
    assert restored.json()["status"] == "abandoned"
    assert restored.json()["turns"][0]["answer"] == "답변 1"
    assert (await client.post(f"/api/interviews/{interview.id}/abandon")).status_code == 204
    await db.refresh(interview)
    assert interview.abandoned_at == first_time
    rejected = await save_answer(db, interview_id=interview.id, turn_no=2, answer_text="늦은 답변")
    assert rejected == TurnRejected.NOT_IN_PROGRESS
    question = await save_question(
        db, interview_id=interview.id, persona="hr_manager", question_text="늦은 질문"
    )
    assert question == TurnRejected.NOT_IN_PROGRESS
    interview_id = interview.id
    await db.rollback()
    # 같은 run의 활성 면접 제한이 풀려 기존 조합의 재도전이 가능하다.
    created = await client.post(f"/api/interviews/{interview_id}/retry")
    assert created.status_code == 201


@pytest.mark.parametrize("status", ["preparing", "completed"])
async def test_abandon_disallowed_state_is_409_and_does_not_change_original(
    client, db, current, status
):
    interview, _ = current
    interview.status = status
    await db.commit()
    response = await client.post(f"/api/interviews/{interview.id}/abandon")
    assert response.status_code == 409
    assert response.json()["error"]["reason"] == "already_completed"
    await db.refresh(interview)
    assert interview.status == status and interview.abandoned_at is None


async def test_abandon_failed_preparation_cannot_be_retried_as_started_interview(
    client, db, current
):
    interview, _ = current
    interview.status = "preparing_failed"
    interview.started_at = None
    interview.current_turn = 0
    interview.last_error = {"recoverable": True, "reason": "prep_failed"}
    await db.commit()
    assert (await client.post(f"/api/interviews/{interview.id}/abandon")).status_code == 204
    await db.refresh(interview)
    assert interview.abandoned_at_turn == 0 and interview.last_error["reason"] == "prep_failed"
    response = await client.post(f"/api/interviews/{interview.id}/retry")
    assert response.status_code == 409
    assert response.json()["error"]["reason"] == "original_not_completed"
    recovery = await client.post(f"/api/interviews/{interview.id}/prepare/retry")
    assert recovery.status_code == 409
    await db.refresh(interview)
    assert interview.status == "abandoned"


@pytest.mark.parametrize("missing", ["invalid", "absent", "other_owner"])
async def test_abandon_unknown_and_foreign_are_404(client, db, current, missing):
    interview, _ = current
    identifier = "not-a-uuid" if missing == "invalid" else str(uuid.uuid4())
    if missing == "other_owner":
        interview.user_id = (await make_user(db)).id
        await db.commit()
        identifier = str(interview.id)
    response = await client.post(f"/api/interviews/{identifier}/abandon")
    assert response.status_code == 404
    assert response.json()["error"]["reason"] == "not_found"


async def test_abandon_requires_login(client):
    response = await client.post(f"/api/interviews/{uuid.uuid4()}/abandon")
    assert response.status_code == 401


async def test_abandon_concurrent_requests_are_idempotent(app, redis, current):
    interview, _ = current

    async def stop():
        async with app.state.session_factory() as session:
            await service.abandon_interview(
                session, redis, user_id=interview.user_id, interview_id=interview.id
            )

    await asyncio.gather(stop(), stop())
    async with app.state.session_factory() as session:
        row = await session.get(InterviewSession, interview.id)
        assert row.status == "abandoned" and row.abandoned_at_turn == 2


async def test_answer_waiting_on_abandon_lock_does_not_store_after_abandon(app, current):
    interview, _ = current
    async with app.state.session_factory() as stopping:
        row = await stopping.get(InterviewSession, interview.id, with_for_update=True)
        row.status = "abandoned"
        row.abandoned_at = datetime.now(UTC)
        row.abandoned_at_turn = 2
        started = asyncio.Event()

        async def submit():
            async with app.state.session_factory() as answering:
                started.set()
                return await save_answer(
                    answering, interview_id=interview.id, turn_no=2, answer_text="동시 늦은 답변"
                )

        task = asyncio.create_task(submit())
        await started.wait()
        await asyncio.sleep(0.1)
        try:
            assert not task.done(), "답변 저장도 중단과 같은 면접 행 잠금을 기다려야 한다"
        finally:
            await stopping.commit()
            outcome = await task
        assert outcome == TurnRejected.NOT_IN_PROGRESS
