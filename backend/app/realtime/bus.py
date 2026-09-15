"""Redis pub/sub 래퍼 (SSE / WS 공용) + Redis 커넥션 단일 진입점.

docs/pipeline.md 3·4절 / task-12

진행 상태 갱신 순서는 Postgres -> Redis mirror -> publish 다 (docs/pipeline.md 2절).
SSE 소비자(task-12)는 아직 없지만 mirror/publish 는 같은 순서로 미리 맞춰 둔다.
"""

import json
from functools import lru_cache
from typing import Any

from redis.asyncio import Redis

from app.core.config import get_settings

#: docs/redis-keys.md
RUN_STEPS_KEY = "run:{run_id}:steps"
RUN_EVENTS_CHANNEL = "run:{run_id}:events"
RUN_LOCK_KEY = "run:lock:{user_id}:analysis:{fingerprint}"
CANDIDATE_PAGE_LOCK_KEY = "cand:lock:{run_id}:{page}"
GITHUB_RATE_LIMIT_KEY = "gh:rl:{github_user_id}"

RUN_STEPS_TTL_SECONDS = 7_200  # 2h
RUN_LOCK_TTL_SECONDS = 1_800  # 30m
CANDIDATE_PAGE_LOCK_TTL_SECONDS = 600  # 10m


@lru_cache(maxsize=1)
def get_redis() -> Redis:
    """프로세스 단위 Redis client. 영구 원본이 아니라 짧은 상태 저장소다."""
    client: Redis = Redis.from_url(get_settings().redis_url, decode_responses=True)
    return client


async def mirror_run_steps(run_id: str, payload: dict[str, str]) -> None:
    """`run:{runId}:steps` 해시 mirror. 비어도 Postgres 에서 재구성할 수 있어야 한다."""
    redis = get_redis()
    key = RUN_STEPS_KEY.format(run_id=run_id)
    await redis.hset(key, mapping=payload)  # type: ignore[misc]
    await redis.expire(key, RUN_STEPS_TTL_SECONDS)


async def publish_run_event(run_id: str, event: dict[str, Any]) -> None:
    """`run:{runId}:events` 로 진행 이벤트를 publish 한다."""
    await get_redis().publish(RUN_EVENTS_CHANNEL.format(run_id=run_id), json.dumps(event))
