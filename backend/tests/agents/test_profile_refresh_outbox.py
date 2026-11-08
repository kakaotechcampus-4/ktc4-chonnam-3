"""프로필 후속 전달의 영속성·중복 인수·유한 복구를 PostgreSQL로 검증한다."""

import asyncio
from datetime import UTC, datetime, timedelta
from importlib import import_module, util
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from redis.exceptions import ConnectionError
from sqlalchemy import func, select, update

from app.db.models import InterviewReport


def api():
    name = "app.features.profile.refresh_outbox"
    assert util.find_spec(name), "성공 보고서의 프로필 갱신 요청은 영구 저장되어야 합니다."
    return import_module(name)


async def seed_report(sessions, seed):
    async with sessions.begin() as db:
        report = InterviewReport(
            interview_session_id=seed["interview_id"],
            headline="총평",
            summary="저장된 보고서",
            total_score=60,
        )
        db.add(report)
        await db.flush()
        return report.id


async def request(sessions, seed, report_id, revision=1):
    async with sessions.begin() as db:
        return await api().ensure_request(
            db, user_id=seed["owner"], report_id=report_id, report_revision=revision
        )


async def read(sessions, identity):
    async with sessions() as db:
        return await db.get(api().ProfileRefreshRequest, identity)


async def test_request_is_transactional_and_one_event_per_report_revision(
    agent_sessions, agent_seed
):
    helper = api()
    report_id = await seed_report(agent_sessions, agent_seed)
    async with agent_sessions() as db:
        await helper.ensure_request(
            db, user_id=agent_seed["owner"], report_id=report_id, report_revision=1
        )
        await db.rollback()
    async with agent_sessions() as db:
        assert await db.scalar(select(func.count()).select_from(helper.ProfileRefreshRequest)) == 0
    first = await request(agent_sessions, agent_seed, report_id)
    assert await request(agent_sessions, agent_seed, report_id) == first
    async with agent_sessions.begin() as db:
        await db.execute(
            update(InterviewReport)
            .where(InterviewReport.id == report_id)
            .values(current_revision=2)
        )
    assert await request(agent_sessions, agent_seed, report_id, 2) != first


async def test_outbox_cannot_bind_a_foreign_user_or_an_unpublished_revision(
    agent_sessions, agent_seed
):
    helper = api()
    report_id = await seed_report(agent_sessions, agent_seed)
    for owner, revision in ((agent_seed["other"], 1), (agent_seed["owner"], 2)):
        async with agent_sessions.begin() as db:
            with pytest.raises(ValueError):
                await helper.ensure_request(
                    db, user_id=owner, report_id=report_id, report_revision=revision
                )


async def test_running_delivery_expiry_rejects_old_ack_and_allows_new_owner(
    agent_sessions, agent_seed
):
    helper = api()
    rid = await request(agent_sessions, agent_seed, await seed_report(agent_sessions, agent_seed))
    redis = AsyncMock()
    await helper.dispatch(agent_sessions, redis, rid)
    old = await helper.claim(agent_sessions, rid, agent_seed["owner"], 1)
    async with agent_sessions.begin() as db:
        await db.execute(
            update(helper.ProfileRefreshRequest)
            .where(helper.ProfileRefreshRequest.id == rid)
            .values(lease_expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
    assert await helper.current(agent_sessions, rid, old) is False
    assert await helper.finish(agent_sessions, rid, old, success=True) is False
    assert await helper.recover(agent_sessions, redis) == 1
    assert await helper.claim(agent_sessions, rid, agent_seed["owner"], 2) is not None


async def test_failed_enqueue_survives_and_recovers_with_bounded_attempts(
    agent_sessions, agent_seed
):
    helper = api()
    rid = await request(agent_sessions, agent_seed, await seed_report(agent_sessions, agent_seed))
    now = datetime.now(UTC) + timedelta(seconds=1)
    redis = AsyncMock()
    redis.enqueue_job.side_effect = ConnectionError("private endpoint must not be recorded")
    assert await helper.dispatch(agent_sessions, redis, rid, now=now) is False
    row = await read(agent_sessions, rid)
    assert row.status == "pending" and row.dispatch_attempts == 1
    assert row.last_error == "queue_unavailable"
    redis.enqueue_job.side_effect = None
    assert await helper.dispatch(agent_sessions, redis, rid, now=row.next_attempt_at) is True
    row = await read(agent_sessions, rid)
    assert row.status == "queued" and row.dispatch_attempts == 2
    redis.enqueue_job.side_effect = ConnectionError("down")
    for _ in range(helper.MAX_DISPATCH_ATTEMPTS):
        row = await read(agent_sessions, rid)
        due = row.lease_expires_at or row.next_attempt_at
        await helper.dispatch(agent_sessions, redis, rid, now=due + timedelta(seconds=1))
    assert (await read(agent_sessions, rid)).status == "failed"


async def test_only_matching_delivery_can_claim_and_old_owner_cannot_ack(
    agent_sessions, agent_seed
):
    helper = api()
    rid = await request(agent_sessions, agent_seed, await seed_report(agent_sessions, agent_seed))
    redis = AsyncMock()
    await helper.dispatch(agent_sessions, redis, rid)
    assert await helper.claim(agent_sessions, rid, agent_seed["other"], 1) is None
    token = await helper.claim(agent_sessions, rid, agent_seed["owner"], 1)
    assert token is not None
    assert await helper.claim(agent_sessions, rid, agent_seed["owner"], 1) is None
    assert await helper.finish(agent_sessions, rid, uuid4(), success=True) is False
    assert await helper.finish(agent_sessions, rid, token, success=True) is True
    assert (await read(agent_sessions, rid)).status == "succeeded"


async def test_redis_loss_after_delivery_is_recovered_and_stale_job_cannot_run(
    agent_sessions, agent_seed
):
    helper = api()
    rid = await request(agent_sessions, agent_seed, await seed_report(agent_sessions, agent_seed))
    redis = AsyncMock()
    await helper.dispatch(agent_sessions, redis, rid)
    row = await read(agent_sessions, rid)
    assert (
        await helper.recover(agent_sessions, redis, now=row.lease_expires_at + timedelta(seconds=1))
        == 1
    )
    assert await helper.claim(agent_sessions, rid, agent_seed["owner"], 1) is None
    assert await helper.claim(agent_sessions, rid, agent_seed["owner"], 2) is not None


async def test_real_redis_worker_claims_durable_delivery_and_acks_once(
    agent_sessions, agent_seed, monkeypatch, test_redis_url
):
    from arq.connections import RedisSettings, create_pool

    from app.workers.tasks import profile_summary as worker

    helper = api()
    rid = await request(agent_sessions, agent_seed, await seed_report(agent_sessions, agent_seed))
    redis = await create_pool(RedisSettings.from_dsn(test_redis_url))
    await redis.flushdb()
    operation = AsyncMock(return_value="role_kept")
    monkeypatch.setattr(worker.service, "refresh_profile_summary", operation)

    class Settings:
        def require_llm(self):
            return object()

    monkeypatch.setattr(worker, "get_settings", Settings)
    try:
        await helper.dispatch(agent_sessions, redis, rid)
        ctx = {"session_factory": agent_sessions, "redis": redis, "http_client": None}
        await worker.profile_summary(ctx, str(agent_seed["owner"]), str(rid), 1)
        await worker.profile_summary(ctx, str(agent_seed["owner"]), str(rid), 1)
        assert operation.await_count == 1
        assert (await read(agent_sessions, rid)).status == "succeeded"
    finally:
        await redis.flushdb()
        await redis.aclose()


async def test_recovery_pages_past_one_hundred_equal_timestamps_once(agent_sessions, agent_seed):
    helper = api()
    report_id = await seed_report(agent_sessions, agent_seed)
    now = datetime.now(UTC)
    async with agent_sessions.begin() as db:
        db.add_all(
            helper.ProfileRefreshRequest(
                user_id=agent_seed["owner"],
                report_id=report_id,
                report_revision=index + 1,
                next_attempt_at=now,
                expires_at=now + timedelta(days=1),
            )
            for index in range(101)
        )
    redis = AsyncMock()
    assert await helper.recover(agent_sessions, redis, now=now + timedelta(seconds=1)) == 101
    assert redis.enqueue_job.await_count == 101
    ids = {call.kwargs["_job_id"] for call in redis.enqueue_job.call_args_list}
    assert len(ids) == 101
    assert await helper.recover(agent_sessions, redis, now=now + timedelta(seconds=1)) == 0


async def test_recovery_total_bound_leaves_remaining_events_durable(agent_sessions, agent_seed):
    helper = api()
    report_id = await seed_report(agent_sessions, agent_seed)
    now = datetime.now(UTC)
    async with agent_sessions.begin() as db:
        db.add_all(
            helper.ProfileRefreshRequest(
                user_id=agent_seed["owner"],
                report_id=report_id,
                report_revision=index + 1,
                next_attempt_at=now,
                expires_at=now + timedelta(days=1),
            )
            for index in range(5)
        )
    redis = AsyncMock()
    assert (
        await helper.recover(
            agent_sessions, redis, now=now + timedelta(seconds=1), page_size=2, max_pages=2
        )
        == 4
    )
    async with agent_sessions() as db:
        assert (
            await db.scalar(
                select(func.count())
                .select_from(helper.ProfileRefreshRequest)
                .where(helper.ProfileRefreshRequest.status == "pending")
