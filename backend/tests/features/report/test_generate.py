"""GET /interviews/{id}/report 생성 흐름 — 202 / 409 / lock / enqueue 실패 / 실패 이력 409.

task-16
"""

import pytest
from redis.exceptions import RedisError
from sqlalchemy import select

from app.db.models.report import ReportGenerationRequest

from ..interview.factories import make_interview, make_repo, make_run, make_turn, make_user
from .factories import make_report


def url(interview_id) -> str:
    return f"/api/interviews/{interview_id}/report"


async def test_202_enqueues_once_with_durable_generation_identity(
    client, db, ctx, enqueue, redis
) -> None:
    interview, _ = ctx

    response = await client.get(url(interview.id))

    assert response.status_code == 202
    assert response.json() == {"status": "generating", "retryAfter": 3}
    request = (await db.scalars(select(ReportGenerationRequest))).one()
    assert (
        request.status == "queued" and request.mode == "initial" and request.expected_revision == 0
    )
    enqueue.assert_awaited_once_with("report_generate", str(interview.id), str(request.id))
    ttl = await redis.ttl(f"report:gen:{interview.id}")
    assert 0 < ttl <= 300


async def test_202_duplicate_lock_skips_enqueue(client, ctx, enqueue) -> None:
    interview, _ = ctx
    first = await client.get(url(interview.id))
    second = await client.get(url(interview.id))

    assert first.status_code == second.status_code == 202
    assert second.json() == {"status": "generating", "retryAfter": 3}
    assert enqueue.await_count == 1


@pytest.mark.parametrize("status", ["preparing", "preparing_failed", "in_progress", "abandoned"])
async def test_409_when_status_not_completed(client, db, ctx, enqueue, status) -> None:
    interview, _ = ctx
    interview.status = status
    await db.commit()

    response = await client.get(url(interview.id))

    assert response.status_code == 409
    assert response.json()["error"]["reason"] == "report_unavailable"
    enqueue.assert_not_called()


async def test_409_when_no_answered_turn(client, db, app, enqueue) -> None:
    user = await make_user(db)
    run = await make_run(db, user)
    interview = await make_interview(db, run, [await make_repo(db, run)], status="completed")
    await make_turn(db, interview, 1)  # asked 만 있다
    await db.commit()
    client.cookies.set("devon_session", await app.state.sessions.create(user.id))

    response = await client.get(url(interview.id))

    assert response.status_code == 409
    assert response.json()["error"]["reason"] == "report_unavailable"
    enqueue.assert_not_called()


async def test_enqueue_failure_releases_lock(client, ctx, enqueue, redis) -> None:
    interview, _ = ctx
    enqueue.side_effect = RedisError("down")

    response = await client.get(url(interview.id))

    assert response.status_code == 500
    assert response.json()["error"]["reason"] == "internal_error"
    assert await redis.exists(f"report:gen:{interview.id}") == 0

    enqueue.side_effect = None  # lock 이 풀려 있어 다음 요청이 다시 enqueue 한다
    assert (await client.get(url(interview.id))).status_code == 202
    assert enqueue.await_count == 2


async def test_409_when_failure_history_exists(client, ctx, enqueue, redis) -> None:
    interview, _ = ctx
    await redis.set(f"report:fail:{interview.id}", "llm_failed")

    response = await client.get(url(interview.id))

    assert response.status_code == 409
    assert response.json()["error"]["reason"] == "report_unavailable"
    enqueue.assert_not_called()
    assert await redis.exists(f"report:gen:{interview.id}") == 0


async def test_failure_history_does_not_block_existing_report(client, db, ctx, redis) -> None:
    interview, _ = ctx
    await make_report(db, interview)
    await db.commit()
    await redis.set(f"report:fail:{interview.id}", "llm_failed")

    assert (await client.get(url(interview.id))).status_code == 200
