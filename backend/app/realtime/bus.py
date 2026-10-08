"""Redis pub/sub 래퍼 (SSE / WS 공용).

docs/pipeline.md 3·4절 / task-12
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Protocol

from redis.asyncio import Redis


class EventSubscription(Protocol):
    """구독 성립 이후 메시지를 읽는 인터페이스. 실제 구현은 redis.asyncio 의 PubSub."""

    # redis.asyncio.PubSub 의 실제 시그니처를 그대로 따른다.
    async def get_message(
        self,
        *,
        ignore_subscribe_messages: bool = True,
        timeout: float | None = None,  # noqa: ASYNC109
    ) -> dict[str, Any] | None: ...


class RedisEventBus:
    """`run:{runId}:events` 같은 채널을 구독·publish 한다. DB 를 모른다."""

    def __init__(self, redis: Redis) -> None:
        """입력: redis.asyncio.Redis 인스턴스. 출력: 없음."""
        self._redis = redis

    @asynccontextmanager
    async def subscribe(self, channel: str) -> AsyncIterator[EventSubscription]:
        """채널을 구독하고 **구독이 실제로 성립한 것을 확인한 뒤** 넘겨준다.

        입력: 채널명. 출력: 메시지를 읽을 수 있는 subscription(비동기 컨텍스트).
        ⚠ 순서가 중요하다 — 구독 확인 전에 Postgres 를 먼저 읽으면 그 사이의 publish 를
        놓친다(docs/pipeline.md 3절 "구독이 먼저다").
        """
        pubsub = self._redis.pubsub()
        try:
            await pubsub.subscribe(channel)
            confirmation = await pubsub.get_message(timeout=5.0)
            if confirmation is None or confirmation.get("type") != "subscribe":
                raise RuntimeError(f"failed to confirm subscription to {channel}")
            yield pubsub
        finally:
            await pubsub.unsubscribe(channel)
            # redis-py 타입 스텁에 aclose() 시그니처가 없다.
            await pubsub.aclose()  # type: ignore[no-untyped-call]

    async def publish(self, channel: str, payload: str) -> None:
        """이벤트 하나를 publish 한다. 입력: 채널명, 직렬화된 payload 문자열. 출력: 없음."""
        await self._redis.publish(channel, payload)
