"""RedisEventBus.subscribe() — 구독 성립 확인, 실패 시 예외, cleanup 순서 (task-12).

실제 Redis 서버 없이 redis.asyncio.Redis 를 autospec mock 으로 대신한다 — FakeBus/
FakeSubscription 을 쓰는 tests/features/test_analysis_events.py 와 달리, 여기서는
`RedisEventBus`(bus.py) 자체의 구현 코드를 직접 실행해서 검증한다.
"""

from unittest import mock

import anyio
import anyio.lowlevel
import pytest
from redis.asyncio import Redis

from app.realtime.bus import RedisEventBus


def _pubsub_mock(*, confirmation: dict[str, object] | None) -> mock.AsyncMock:
    pubsub = mock.AsyncMock()
    pubsub.get_message = mock.AsyncMock(return_value=confirmation)
    return pubsub


def _redis_with_pubsub(pubsub: mock.AsyncMock) -> Redis:
    redis = mock.create_autospec(Redis, instance=True)
    redis.pubsub = mock.MagicMock(return_value=pubsub)
    return redis


async def test_subscribe_confirms_before_yielding() -> None:
    pubsub = _pubsub_mock(confirmation={"type": "subscribe", "channel": "run:1:events"})
    bus = RedisEventBus(_redis_with_pubsub(pubsub))

    async with bus.subscribe("run:1:events") as subscription:
        assert subscription is pubsub

    pubsub.subscribe.assert_awaited_once_with("run:1:events")
    pubsub.get_message.assert_awaited_once_with(timeout=5.0)


async def test_subscribe_raises_when_confirmation_missing() -> None:
    pubsub = _pubsub_mock(confirmation=None)
    bus = RedisEventBus(_redis_with_pubsub(pubsub))

    with pytest.raises(RuntimeError, match="run:1:events"):
        async with bus.subscribe("run:1:events"):
            pass


async def test_subscribe_raises_when_confirmation_is_wrong_type() -> None:
    """다른 종류의 메시지(예: 이미 온 이벤트)를 구독 확인으로 착각하면 안 된다."""
    pubsub = _pubsub_mock(confirmation={"type": "message", "data": "..."})
    bus = RedisEventBus(_redis_with_pubsub(pubsub))

    with pytest.raises(RuntimeError):
        async with bus.subscribe("run:1:events"):
            pass


async def test_subscribe_unsubscribes_and_closes_even_on_exception() -> None:
    """본문에서 예외가 나도 unsubscribe/aclose 는 반드시 실행돼야 한다(연결 누수 방지)."""
    pubsub = _pubsub_mock(confirmation={"type": "subscribe"})
    bus = RedisEventBus(_redis_with_pubsub(pubsub))

    with pytest.raises(ValueError, match="boom"):
        async with bus.subscribe("run:1:events"):
            raise ValueError("boom")

    pubsub.unsubscribe.assert_awaited_once_with("run:1:events")
    pubsub.aclose.assert_awaited_once()


async def test_subscribe_cleans_up_even_when_confirmation_fails() -> None:
    """구독 확인 실패로 RuntimeError 를 던지기 전에 이미 subscribe() 는 성공했으므로 정리한다."""
    pubsub = _pubsub_mock(confirmation=None)
    bus = RedisEventBus(_redis_with_pubsub(pubsub))

    with pytest.raises(RuntimeError):
        async with bus.subscribe("run:1:events"):
            pass

    pubsub.unsubscribe.assert_awaited_once_with("run:1:events")
    pubsub.aclose.assert_awaited_once()


async def test_subscribe_closes_even_when_unsubscribe_fails() -> None:
    """unsubscribe 가 예외를 던져도 aclose 는 호출돼 연결이 풀에 반환돼야 한다."""
    pubsub = _pubsub_mock(confirmation={"type": "subscribe"})
    pubsub.unsubscribe.side_effect = ConnectionError("socket closed")
    bus = RedisEventBus(_redis_with_pubsub(pubsub))

    with pytest.raises(ConnectionError):
        async with bus.subscribe("run:1:events"):
            pass

    pubsub.aclose.assert_awaited_once()


async def test_subscribe_cleanup_completes_when_cancelled() -> None:
    """SSE 접속 종료(AnyIO 취소) 중에도 unsubscribe→aclose 가 끝까지 실행돼야 한다."""
    pubsub = _pubsub_mock(confirmation={"type": "subscribe"})
    finished: list[str] = []

    async def unsubscribe(channel: str) -> None:
        await anyio.lowlevel.checkpoint()  # 취소가 걸리면 여기서 중단된다
        finished.append("unsubscribe")

    async def aclose() -> None:
        await anyio.lowlevel.checkpoint()
        finished.append("aclose")

    pubsub.unsubscribe.side_effect = unsubscribe
    pubsub.aclose.side_effect = aclose
    bus = RedisEventBus(_redis_with_pubsub(pubsub))
    entered = anyio.Event()

    async def consume() -> None:
        async with bus.subscribe("run:1:events"):
            entered.set()
            await anyio.sleep_forever()

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(consume)
        await entered.wait()
        task_group.cancel_scope.cancel()

    assert finished == ["unsubscribe", "aclose"]


async def test_publish_forwards_to_redis() -> None:
    redis = mock.create_autospec(Redis, instance=True)
    redis.publish = mock.AsyncMock()
    bus = RedisEventBus(redis)

    await bus.publish("run:1:events", '{"type":"completed"}')

    redis.publish.assert_awaited_once_with("run:1:events", '{"type":"completed"}')
