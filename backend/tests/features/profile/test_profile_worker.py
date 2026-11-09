"""profile_summary worker: lock·실패 분리·이전 요약 유지. LLM 은 대역이다. task-16"""

import asyncio
from unittest.mock import AsyncMock

import pytest

from app.llm_tasks import profile_summary as tasks
from app.workers.tasks import profile_summary as worker
from app.workers.tasks import report_generate as report_worker

from ..interview.factories import make_repo
from .fakes import LLM, ROLE, FakeGenerator, completed_interview, read_summary, refresh_summary


@pytest.fixture
def worker_env(app, monkeypatch):
    class _Settings:
        def require_llm(self):
            return LLM

    monkeypatch.setattr(worker, "get_settings", lambda: _Settings())
    return {
        "session_factory": app.state.session_factory,
        "http_client": None,
        "redis": app.state.redis,
    }


async def test_worker_runs_and_releases_lock(app, db, world, worker_env, monkeypatch):
    user, run = world
    repo = await make_repo(db, run, languages={"Python": 1})
    await completed_interview(db, run, [repo])
    generator = FakeGenerator()
    monkeypatch.setattr(tasks, "generate_role_summary", generator)
    await worker.profile_summary(worker_env, str(user.id))
    assert len(generator.calls) == 1
    assert (await read_summary(db, user)).role_summary == ROLE
    assert await app.state.redis.exists(f"profile:gen:{user.id}") == 0


async def test_worker_skips_when_lock_is_held(app, db, world, worker_env, monkeypatch):
    user, run = world
    repo = await make_repo(db, run, languages={"Python": 1})
    await completed_interview(db, run, [repo])
    generator = FakeGenerator()
    monkeypatch.setattr(tasks, "generate_role_summary", generator)
    await app.state.redis.set(f"profile:gen:{user.id}", "1", ex=600)
    await worker.profile_summary(worker_env, str(user.id))
    assert generator.calls == []
    assert await read_summary(db, user) is None
    assert await app.state.redis.exists(f"profile:gen:{user.id}") == 1
    assert await app.state.redis.get(f"profile:dirty:{user.id}") == b"1"


async def test_worker_failure_does_not_raise_and_keeps_summary(
    app, db, world, worker_env, monkeypatch
):
    user, run = world
    first = await make_repo(db, run, languages={"Python": 1})
    await completed_interview(db, run, [first])
    await refresh_summary(app, user, FakeGenerator())
    second = await make_repo(db, run, languages={"Java": 1})
    await completed_interview(db, run, [second])
    monkeypatch.setattr(tasks, "generate_role_summary", FakeGenerator(error=RuntimeError("boom")))
    await worker.profile_summary(worker_env, str(user.id))
    summary = await read_summary(db, user)
    assert summary.role_summary == ROLE
    assert summary.based_repo_ids == [first.id]
    assert await app.state.redis.exists(f"profile:gen:{user.id}") == 0


async def test_concurrent_new_report_refreshes_after_active_snapshot(
    app, db, world, worker_env, monkeypatch
):
    user, run = world
    first = await make_repo(db, run, languages={"Python": 1})
    await completed_interview(db, run, [first])
    started, finish = asyncio.Event(), asyncio.Event()
    calls = []

    async def generate(payload, **kwargs):
        calls.append(payload)
        if len(calls) == 1:
            started.set()
            await finish.wait()
        return ROLE

    monkeypatch.setattr(tasks, "generate_role_summary", generate)
    enqueue = AsyncMock()
    monkeypatch.setattr(app.state.redis, "enqueue_job", enqueue)
    active = asyncio.create_task(worker.profile_summary(worker_env, str(user.id)))
    await asyncio.wait_for(started.wait(), 5)
    try:
        second = await make_repo(db, run, languages={"Go": 1})
        await completed_interview(db, run, [second])
        # 같은 사용자에 여러 report가 도착해도 진행 중인 집계는 겹쳐 실행하지 않는다.
        await asyncio.gather(*(worker.profile_summary(worker_env, str(user.id)) for _ in range(3)))
        assert len(calls) == 1
    finally:
        finish.set()
        await asyncio.wait_for(active, 5)
    assert enqueue.await_count == 1
    follow_up_id = enqueue.call_args.kwargs["_job_id"]
    assert follow_up_id.startswith(f"profile_summary:{user.id}:refresh:")
    assert await app.state.redis.exists(f"profile:dirty:{user.id}") == 0
    await worker.profile_summary(worker_env, str(user.id))
    assert (await read_summary(db, user)).based_repo_ids == sorted([first.id, second.id])
    assert len(calls) == 2


async def test_failure_without_new_event_never_enqueues_retry(
    app, db, world, worker_env, monkeypatch
):
    user, run = world
    await completed_interview(db, run, [await make_repo(db, run, languages={"Python": 1})])
    monkeypatch.setattr(
        tasks, "generate_role_summary", FakeGenerator(error=RuntimeError("timeout"))
    )
    enqueue = AsyncMock()
    monkeypatch.setattr(app.state.redis, "enqueue_job", enqueue)
    await worker.profile_summary(worker_env, str(user.id))
    enqueue.assert_not_awaited()


async def test_new_report_event_survives_active_generation_failure(
    app, db, world, worker_env, monkeypatch
):
    user, run = world
    await completed_interview(db, run, [await make_repo(db, run, languages={"Python": 1})])
    started, finish = asyncio.Event(), asyncio.Event()

    async def fail(*args, **kwargs):
        started.set()
        await finish.wait()
        raise RuntimeError("timeout")

    monkeypatch.setattr(tasks, "generate_role_summary", fail)
    enqueue = AsyncMock()
    monkeypatch.setattr(app.state.redis, "enqueue_job", enqueue)
    active = asyncio.create_task(worker.profile_summary(worker_env, str(user.id)))
    await asyncio.wait_for(started.wait(), 5)
    try:
        await worker.profile_summary(worker_env, str(user.id))
    finally:
        finish.set()
        await asyncio.wait_for(active, 5)
    assert enqueue.await_count == 1
    assert await read_summary(db, user) is None


async def test_replaced_owner_cannot_save_or_delete_new_owner_lock(
    app, db, world, worker_env, monkeypatch
):
    user, run = world
    await completed_interview(db, run, [await make_repo(db, run, languages={"Python": 1})])

    async def steal_during_generation(*args, **kwargs):
        await app.state.redis.set(f"profile:gen:{user.id}", "new-owner", ex=600)
        return ROLE

    monkeypatch.setattr(tasks, "generate_role_summary", steal_during_generation)
    await worker.profile_summary(worker_env, str(user.id))
    assert await read_summary(db, user) is None
    assert await app.state.redis.get(f"profile:gen:{user.id}") == b"new-owner"


async def test_heartbeat_keeps_lock_during_slow_generation(app, db, world, worker_env, monkeypatch):
    user, run = world
    await completed_interview(db, run, [await make_repo(db, run, languages={"Python": 1})])
    monkeypatch.setattr(worker.service, "PROFILE_LOCK_TTL_SECONDS", 1)

    async def slow(*args, **kwargs):
        token = await app.state.redis.get(f"profile:gen:{user.id}")
        await asyncio.sleep(1.4)
        assert await app.state.redis.get(f"profile:gen:{user.id}") == token
        return ROLE

    monkeypatch.setattr(tasks, "generate_role_summary", slow)
    await worker.profile_summary(worker_env, str(user.id))
    assert (await read_summary(db, user)).role_summary == ROLE


async def test_retained_arq_result_does_not_block_different_report(app, db, world):
    user, run = world
    repo = await make_repo(db, run, languages={"Python": 1})
    first = await completed_interview(db, run, [repo])
    second = await completed_interview(db, run, [repo])
    first_id = f"profile_summary:{user.id}:{first.id}"
    second_id = f"profile_summary:{user.id}:{second.id}"
    await app.state.redis.set(f"arq:result:{first_id}", b"retained", ex=3600)
    ctx = {"session_factory": app.state.session_factory, "redis": app.state.redis}

    await report_worker._enqueue_profile_summary(ctx, first.id)
    await report_worker._enqueue_profile_summary(ctx, second.id)

    assert await app.state.redis.exists(f"arq:job:{second_id}") == 1
    assert await app.state.redis.get(f"arq:result:{first_id}") == b"retained"
