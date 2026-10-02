"""stream_run_progress — 구독→스냅샷 순서, step 중복 제거, 종료 처리, poll 폴백 (task-12).

실제 Redis 없이 검증할 수 있도록 `FakeSubscription`/`FakeBus` 로 RedisEventBus 를 대신한다.
"""

import json
from collections.abc import AsyncIterator, Awaitable, Callable

from app.features.analysis.events import RunSnapshot, StepState, stream_run_progress


class FakeSubscription:
    """큐에 넣어둔 메시지를 순서대로 돌려주는 가짜 구독. 큐가 비면 None(=timeout)을 돌려준다."""

    def __init__(self, messages: list[dict[str, str] | None]) -> None:
        self._messages = list(messages)

    async def get_message(
        self,
        *,
        ignore_subscribe_messages: bool = True,
        timeout: float | None = None,  # noqa: ASYNC109 — redis.asyncio.PubSub 시그니처를 따른다
    ) -> dict[str, str] | None:
        if not self._messages:
            return None
        return self._messages.pop(0)


class FakeBus:
    """`bus.subscribe(channel)` 호출 순서를 기록하고 미리 준비된 subscription 을 돌려준다."""

    def __init__(self, subscription: FakeSubscription) -> None:
        self._subscription = subscription
        self.subscribed_channels: list[str] = []

    def subscribe(self, channel: str):
        self.subscribed_channels.append(channel)
        return _AsyncCM(self._subscription)


class _AsyncCM:
    def __init__(self, value: object) -> None:
        self._value = value

    async def __aenter__(self):
        return self._value

    async def __aexit__(self, *exc_info):
        return False


def _message(payload: dict[str, object]) -> dict[str, str]:
    return {"type": "message", "data": json.dumps(payload)}


async def _collect(iterator: AsyncIterator[dict[str, object]]) -> list[dict[str, object]]:
    return [event async for event in iterator]


def _snapshot(status: str, *steps: tuple[str, str]) -> Callable[[], Awaitable[RunSnapshot]]:
    result = RunSnapshot(status=status, steps=tuple(StepState(s, st) for s, st in steps))

    async def read() -> RunSnapshot:
        return result

    return read


async def test_subscribes_before_reading_snapshot() -> None:
    bus = FakeBus(FakeSubscription([]))
    order: list[str] = []

    async def read_snapshot() -> RunSnapshot:
        order.append("snapshot")
        return RunSnapshot(status="succeeded", steps=())

    events = stream_run_progress("run-1", bus=bus, read_snapshot=read_snapshot)
    await _collect(events)

    assert bus.subscribed_channels == ["run:run-1:events"]
    assert order == ["snapshot"]


async def test_sends_initial_snapshot_steps_then_stops_if_already_terminal() -> None:
    bus = FakeBus(FakeSubscription([]))
    read_snapshot = _snapshot("succeeded", ("repo_select", "completed"))

    events = await _collect(stream_run_progress("run-1", bus=bus, read_snapshot=read_snapshot))

    assert events[0] == {
        "event": "step",
        "data": json.dumps({"step": "repo_select", "status": "completed"}),
    }
    assert events[-1]["event"] == "completed"


async def test_partial_and_failed_both_map_to_failed_event() -> None:
    for job_status in ("partial", "failed", "canceled"):
        bus = FakeBus(FakeSubscription([]))
        read_snapshot = _snapshot(job_status)

        events = await _collect(stream_run_progress("run-1", bus=bus, read_snapshot=read_snapshot))

        assert events[-1]["event"] == "failed", job_status


async def test_step_event_from_message_is_forwarded() -> None:
    bus = FakeBus(
        FakeSubscription(
            [
                _message({"type": "step", "step": "jd_fetch", "status": "running"}),
                _message({"type": "completed"}),
            ]
        )
    )
    read_snapshot = _snapshot("running")

    events = await _collect(stream_run_progress("run-1", bus=bus, read_snapshot=read_snapshot))

    step_events = [e for e in events if e["event"] == "step"]
    assert json.loads(step_events[-1]["data"]) == {"step": "jd_fetch", "status": "running"}


async def test_duplicate_step_status_is_not_sent_twice() -> None:
    duplicate = _message({"type": "step", "step": "jd_fetch", "status": "running"})
    # 두 번째 duplicate 이후엔 completed 로 스트림을 끊는다(무한 대기 방지).
    bus = FakeBus(FakeSubscription([duplicate, duplicate, _message({"type": "completed"})]))
    read_snapshot = _snapshot("running", ("jd_fetch", "running"))

    events = await _collect(stream_run_progress("run-1", bus=bus, read_snapshot=read_snapshot))

    step_events = [e for e in events if e["event"] == "step"]
    # snapshot 에서 이미 (jd_fetch, running) 을 냈으므로 message 두 번은 전부 중복 제거된다.
    assert len(step_events) == 1


async def test_completed_message_ends_stream() -> None:
    bus = FakeBus(FakeSubscription([_message({"type": "completed"})]))
    read_snapshot = _snapshot("running")

    events = await _collect(stream_run_progress("run-1", bus=bus, read_snapshot=read_snapshot))

    assert events[-1] == {"event": "completed", "data": json.dumps({"status": "succeeded"})}


async def test_failed_message_carries_reason_and_ends_stream() -> None:
    bus = FakeBus(FakeSubscription([_message({"type": "failed", "reason": "jd_fetch_failed"})]))
    read_snapshot = _snapshot("running")

    events = await _collect(stream_run_progress("run-1", bus=bus, read_snapshot=read_snapshot))

    assert events[-1] == {
        "event": "failed",
        "data": json.dumps({"status": "failed", "reason": "jd_fetch_failed"}),
    }


async def test_message_timeout_falls_back_to_postgres_poll() -> None:
    """message 가 안 와도(timeout=None) Postgres 를 재확인해 종료 상태를 놓치지 않는다."""
    bus = FakeBus(FakeSubscription([None, None]))
    calls = {"n": 0}

    async def read_snapshot() -> RunSnapshot:
        calls["n"] += 1
        if calls["n"] == 1:
            return RunSnapshot(status="running", steps=())
        return RunSnapshot(status="succeeded", steps=())

    events = await _collect(stream_run_progress("run-1", bus=bus, read_snapshot=read_snapshot))

    assert events[-1]["event"] == "completed"
    assert calls["n"] == 2
