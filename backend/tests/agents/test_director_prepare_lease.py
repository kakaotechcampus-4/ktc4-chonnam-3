"""실제 DB의 만료 회수·heartbeat·늦은 결과가 첫 질문을 중복 저장하지 않게 한다."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import select

from app.db.models import InterviewSession, InterviewTurn, LLMCallRecord
from app.features.interview import prepare, prepare_lease
from app.features.interview.service import retry_prepare
from app.workers.tasks.interview_preparation_reaper import recover_preparations
from tests.agents.test_director_prepare import Transport, run, settings
from tests.agents.test_director_prepare import ready as ready
from tests.agents.test_director_prepare_recovery import Broker


async def test_reaper_without_new_job_closes_only_expired_owner_and_allows_retry(
    agent_sessions, ready
):
    call_id, job_id = uuid4(), uuid4()
    async with agent_sessions.begin() as db:
        row = await db.get(InterviewSession, ready["interview_id"])
        row.context_state = {
            "prepare_job_id": str(job_id),
            "prepare_lease_expires_at": (datetime.now(UTC) - timedelta(seconds=1)).isoformat(),
            "prepare_director_call_id": str(call_id),
        }
        db.add(
            LLMCallRecord(
                id=call_id,
                interview_session_id=row.id,
                turn_no=1,
                task_name="director",
                attempts=[],
            )
        )
    assert await recover_preparations(agent_sessions) == 1
    assert await recover_preparations(agent_sessions) == 0
    async with agent_sessions() as db:
        row = await db.get(InterviewSession, ready["interview_id"])
        assert row.status == "preparing_failed"
        assert row.last_error["code"] == "preparation_lease_expired"
        assert not prepare_lease.CLAIM_KEYS.intersection(row.context_state)
        assert (await db.get(LLMCallRecord, call_id)).discard_reason == "preparation_lease_expired"
        await retry_prepare(db, Broker(), user_id=ready["owner"], interview_id=row.id)
    assert await run(agent_sessions, ready, Transport(ready))


async def test_live_heartbeat_prevents_reaping_during_external_io(
    agent_sessions, ready, monkeypatch
):
    monkeypatch.setattr(prepare_lease, "HEARTBEAT_SECONDS", 0.05)
    started = asyncio.Event()
    release = asyncio.Event()
    refreshed = asyncio.Event()
    transport = Transport(ready)
    original_refresh = prepare_lease.refresh

    async def observe(*args):
        result = await original_refresh(*args)
        if result:
            refreshed.set()
        return result

    monkeypatch.setattr(prepare_lease, "refresh", observe)

    async def slow(request):
        if not started.is_set():
            started.set()
            await release.wait()
        return await transport(request)

    task = asyncio.create_task(run(agent_sessions, ready, slow))
    await asyncio.wait_for(started.wait(), 5)
    async with agent_sessions() as db:
        row = await db.get(InterviewSession, ready["interview_id"])
        original_expiry = prepare_lease.expires(row)
    refreshed.clear()
    await asyncio.wait_for(refreshed.wait(), 5)
    assert await recover_preparations(agent_sessions, now=original_expiry) == 0
    release.set()
    assert await asyncio.wait_for(task, 10)


async def test_replaced_owner_cannot_store_late_director_question(agent_sessions, ready):
    entered, release = asyncio.Event(), asyncio.Event()
    old_transport = Transport(ready)

    async def late(request):
        if request.method == "POST" and not entered.is_set():
            entered.set()
            await release.wait()
        return await old_transport(request)

    async def old_run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(late)) as http:
            return await prepare.prepare_interview(
                agent_sessions,
                user_id=ready["owner"],
                interview_id=ready["interview_id"],
                settings=settings().model_copy(update={"llm_timeout_seconds": 60}),
                http_client=http,
            )

    old = asyncio.create_task(old_run())
    await asyncio.wait_for(entered.wait(), 10)
    async with agent_sessions.begin() as db:
        row = await db.get(InterviewSession, ready["interview_id"])
        old_call = UUID(row.context_state["prepare_director_call_id"])
        row.context_state = {
            **row.context_state,
            "prepare_lease_expires_at": (datetime.now(UTC) - timedelta(seconds=1)).isoformat(),
        }
    assert await recover_preparations(agent_sessions) == 1
    async with agent_sessions() as db:
        await retry_prepare(
            db, Broker(), user_id=ready["owner"], interview_id=ready["interview_id"]
        )
    new_transport = Transport(ready)
    assert await run(agent_sessions, ready, new_transport)
    release.set()
    assert await asyncio.wait_for(old, 10) is False
    async with agent_sessions() as db:
        turns = (await db.scalars(select(InterviewTurn))).all()
        assert len(turns) == 1
        record = await db.get(LLMCallRecord, old_call)
        assert record.discard_reason == "context_changed"
        assert len(record.attempts) == 2
    assert new_transport.github == []


def test_prepare_maximum_allowed_timeouts_fit_actual_worker_budget():
    prepare_lease.validate_timeout(30, 127.5)
    with pytest.raises(prepare_lease.PreparationTimeoutError):
        prepare_lease.validate_timeout(30, 127.6)
    with pytest.raises(prepare_lease.PreparationTimeoutError):
        prepare_lease.validate_timeout(300, 1)


@pytest.mark.parametrize("age, expected", [(100, 0), (601, 1)])
@pytest.mark.parametrize("claimed", [False, True, "malformed"])
async def test_legacy_claim_has_worker_timeout_grace_and_pending_recovery(
    agent_sessions, ready, age, expected, claimed
):
    call_id = uuid4()
    async with agent_sessions.begin() as db:
        row = await db.get(InterviewSession, ready["interview_id"])
        row.context_state = {"prepare_job_id": str(uuid4())} if claimed else {}
        if claimed == "malformed":
            row.context_state = {**row.context_state, "prepare_director_call_id": "invalid"}
        row.updated_at = datetime.now(UTC) - timedelta(seconds=age)
        db.add(
            LLMCallRecord(
                id=call_id,
                interview_session_id=row.id,
                turn_no=1,
                task_name="director",
                attempts=[],
            )
        )
    assert await recover_preparations(agent_sessions) == expected
    async with agent_sessions() as db:
        row = await db.get(InterviewSession, ready["interview_id"])
        record = await db.get(LLMCallRecord, call_id)
        if expected:
            assert row.status == "preparing_failed"
            assert record.discard_reason == "preparation_lease_expired"
            await retry_prepare(db, Broker(), user_id=ready["owner"], interview_id=row.id)
        else:
            assert row.status == "preparing" and record.discard_reason is None
    if expected:
        assert await run(agent_sessions, ready, Transport(ready))
