"""소켓 교체와 별개인 답변 작업의 유한 수명을 검사한다."""

import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest
from redis.asyncio import Redis

from app.core.config import Settings
from app.features.interview import ws
from app.features.interview.agent_context import AgentStateError
from app.features.interview.director_service import AnswerExecution


class WorkRedis:
    def __init__(self):
        self.now = 0
        self.owner = None
        self.expiry = 0
        self.releases = []

    async def execute_command(self, command, script, count, *args):
        if script == ws._BEGIN_WORK:
            self.owner, seconds = args[4], args[-1]
            self.expiry = self.now + seconds
        elif script == ws._RELEASE:
            self.releases.append(args[-1])
            if self.owner == args[-1]:
                self.owner = None
        elif count == 1:
            if self.owner != args[-2] or self.now >= self.expiry:
                return 0
            self.expiry = self.now + args[-1]
        return 1

    async def exists(self, key):
        return self.owner is not None and self.now < self.expiry


def connection(redis):
    config = Settings(
        _env_file=None,
        openai_api_key="fixture",
        llm_timeout_seconds=100,
        llm_max_output_tokens=2048,
        llm_max_input_bytes=262144,
        llm_max_response_bytes=262144,
        tavily_timeout_seconds=50,
    )
    socket = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(settings=config, http_client=None, session_factory=None)
        )
    )
    return ws._Connection(socket, redis, "session", uuid4(), b"session", "accepted-owner")


async def test_legal_slow_processing_keeps_work_during_socket_takeover(monkeypatch):
    redis = WorkRedis()
    old = connection(redis)
    entered, release = asyncio.Event(), asyncio.Event()
    calls = []

    async def read_state(*args):
        question = {"type": "question", "turn": 2 if release.is_set() else 1}
        if entered.is_set() and not release.is_set():
            question = None
        return ws._State("in_progress", question, {}, None, (), "text")

    async def process(*args, **kwargs):
        calls.append(kwargs["call_id"])
        entered.set()
        await release.wait()
        return AnswerExecution(kwargs["call_id"], uuid4(), uuid4(), False, None, None, True)

    monkeypatch.setattr(ws, "_WORK_HEARTBEAT_SECONDS", 0.001, raising=False)
    monkeypatch.setattr(ws, "_read_state", read_state)
    monkeypatch.setattr(ws, "process_answer", process)
    running = asyncio.create_task(ws._execute(old, uuid4(), 1, "답변", answer_mode="text"))
    await entered.wait()
    try:
        # T3 두 시도와 Retry-After, 외부 search/extract, 최초·자동 T4가 모두 허용 범위다.
        for instant in range(9, 730, 9):
            redis.now = instant
            await asyncio.sleep(0.003)
        assert redis.now == 729 and await redis.exists(old.work)
        old.connected = False
        new = connection(redis)
        new.nonce = "replacement-owner"
        events = []

        async def send(event):
            events.append(event)

        async def close(*args):
            new.connected = False

        new.send, new.close = send, close
        restoring = asyncio.create_task(new.restore(uuid4()))
        await asyncio.sleep(0.02)
        assert not restoring.done() and events == []
        release.set()
        await running
        assert await restoring
        assert events == [{"type": "question", "turn": 2}]
        assert len(calls) == 1 and redis.owner is None
    finally:
        release.set()
        await running


@pytest.mark.parametrize("stop", ["deadline", "cancel"])
async def test_work_cleanup_finishes_before_owner_marker_release(monkeypatch, stop):
    redis, entered, cleaned = WorkRedis(), asyncio.Event(), asyncio.Event()
    old = connection(redis)

    async def read_state(*args):
        return ws._State("in_progress", {"turn": 1}, {}, None, (), "text")

    async def process(*args, **kwargs):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            await asyncio.sleep(0.005)
            assert redis.owner == old.nonce and redis.releases == []
            cleaned.set()

    monkeypatch.setattr(ws, "_answer_work_seconds", lambda *args: 0.02, raising=False)
    monkeypatch.setattr(ws, "_read_state", read_state)
    monkeypatch.setattr(ws, "process_answer", process)
    running = asyncio.create_task(ws._execute(old, uuid4(), 1, "답변", answer_mode="text"))
    await entered.wait()
    if stop == "cancel":
        running.cancel()
    expected = AgentStateError if stop == "deadline" else asyncio.CancelledError
    try:
        with pytest.raises(expected):
            await asyncio.wait_for(running, 1)
        assert cleaned.is_set() and redis.owner is None
    finally:
        running.cancel()
        await asyncio.gather(running, return_exceptions=True)


def test_work_deadline_includes_task_overrides_retry_wait_and_full_external_budget():
    config = connection(WorkRedis()).socket.app.state.settings
    config.llm_task_timeouts = {"answer_analysis": 100, "director": 120}
    config.tavily_max_calls, config.external_max_calls_per_interview = 8, 3

    assert (
        ws._answer_work_seconds(config, config.require_llm()) == 3 * 100 + 4 * 120 + 8 + 3 * 50 + 30
    )


async def test_old_work_owner_cannot_refresh_or_delete_replacement_marker(monkeypatch):
    redis, entered = WorkRedis(), asyncio.Event()
    old = connection(redis)

    async def read_state(*args):
        return ws._State("in_progress", {"turn": 1}, {}, None, (), "text")

    async def process(*args, **kwargs):
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(ws, "_WORK_HEARTBEAT_SECONDS", 0.001)
    monkeypatch.setattr(ws, "_read_state", read_state)
    monkeypatch.setattr(ws, "process_answer", process)
    running = asyncio.create_task(ws._execute(old, uuid4(), 1, "답변", answer_mode="text"))
    await entered.wait()
    redis.owner, redis.expiry = "new-work-owner", 500
    with pytest.raises(AgentStateError, match="answer_work_ownership_lost"):
        await asyncio.wait_for(running, 1)
    assert (redis.owner, redis.expiry) == ("new-work-owner", 500)


async def test_work_lua_scripts_compare_nonce_on_real_redis(test_redis_url):
    redis = Redis.from_url(test_redis_url)
    key = "ws:work:nonce-test:" + uuid4().hex
    try:
        await redis.set(key, "new-owner", ex=30)
        assert await ws._script(redis, ws._REFRESH_WORK, 1, key, "old-owner", 1) == 0
        assert await redis.ttl(key) > 25
        assert await ws._script(redis, ws._RELEASE, 1, key, "old-owner") == 0
        assert await redis.get(key) == b"new-owner"
        assert await ws._script(redis, ws._REFRESH_WORK, 1, key, "new-owner", 30) == 1
        assert await ws._script(redis, ws._RELEASE, 1, key, "new-owner") == 1
    finally:
        await redis.delete(key)
        await redis.aclose()


async def test_repeated_cancellation_waits_for_cleanup_before_releasing_work(monkeypatch):
    redis = WorkRedis()
    old = connection(redis)
    entered, cleaning, release, cleaned = (asyncio.Event() for _ in range(4))

    async def read_state(*args):
        return ws._State("in_progress", {"turn": 1}, {}, None, (), "text")

    async def process(*args, **kwargs):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleaning.set()
            await release.wait()
            assert redis.owner == old.nonce
            cleaned.set()

    monkeypatch.setattr(ws, "_read_state", read_state)
    monkeypatch.setattr(ws, "process_answer", process)
    running = asyncio.create_task(ws._execute(old, uuid4(), 1, "답변", answer_mode="text"))
    await entered.wait()
    running.cancel()
    await cleaning.wait()
    running.cancel()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await running
    assert cleaned.is_set() and redis.owner is None


async def test_stuck_cleanup_stops_heartbeat_and_keeps_marker_until_lease_expires(monkeypatch):
    redis = WorkRedis()
    old = connection(redis)
    entered, release, ended = (asyncio.Event() for _ in range(3))

    async def read_state(*args):
        return ws._State("in_progress", {"turn": 1}, {}, None, (), "text")

    async def process(*args, **kwargs):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            try:
                await release.wait()
            finally:
                ended.set()

    monkeypatch.setattr(ws, "_read_state", read_state)
    monkeypatch.setattr(ws, "process_answer", process)
    monkeypatch.setattr(ws, "_WORK_CLEANUP_SECONDS", 0.02, raising=False)
    running = asyncio.create_task(ws._execute(old, uuid4(), 1, "답변", answer_mode="text"))
    await entered.wait()
    fallback = asyncio.get_running_loop().call_later(0.2, release.set)
    try:
        running.cancel()
        with pytest.raises(AgentStateError, match="answer_work_cleanup_timeout"):
            await running
        await asyncio.wait_for(ended.wait(), 1)
        assert redis.owner == old.nonce and redis.releases == []
        redis.now = redis.expiry + 1
        assert not await redis.exists(old.work)
    finally:
        fallback.cancel()
        release.set()
        await asyncio.gather(running, return_exceptions=True)
