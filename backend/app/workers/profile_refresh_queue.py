"""사용자별 프로필 집계를 직렬화하고 새 보고서의 갱신 신호를 합친다."""

import secrets
from collections.abc import Awaitable, Callable
from typing import cast

from arq.connections import ArqRedis

_ACQUIRE = """
if redis.call('EXISTS', KEYS[1]) == 1 then
  redis.call('SET', KEYS[2], '1')
  return 0
end
redis.call('SET', KEYS[1], ARGV[1], 'PX', ARGV[2])
redis.call('DEL', KEYS[2])
return 1
"""
_RENEW = """
if redis.call('GET', KEYS[1]) ~= ARGV[1] then return 0 end
return redis.call('PEXPIRE', KEYS[1], ARGV[2])
"""
_RELEASE = """
if redis.call('GET', KEYS[1]) ~= ARGV[1] then return -1 end
redis.call('DEL', KEYS[1])
local dirty = redis.call('EXISTS', KEYS[2])
redis.call('DEL', KEYS[2])
return dirty
"""


class ProfileRefreshLease:
    def __init__(self, redis: ArqRedis, user_id: str, ttl_seconds: int):
        self.redis, self.user_id, self.ttl_seconds = redis, user_id, ttl_seconds
        self.key, self.dirty_key = f"profile:gen:{user_id}", f"profile:dirty:{user_id}"
        self.token = secrets.token_hex(24)

    async def _eval(self, script: str, *args: object) -> object:
        execute = cast(Callable[..., Awaitable[object]], self.redis.execute_command)
        return await execute("EVAL", script, 2, self.key, self.dirty_key, self.token, *args)

    async def acquire(self) -> bool:
        return await self._eval(_ACQUIRE, self.ttl_seconds * 1000) == 1

    async def renew(self) -> bool:
        return await self._eval(_RENEW, self.ttl_seconds * 1000) == 1

    async def current(self) -> bool:
        # 저장 직전 확인도 임대를 연장한다. 다른 소유자의 토큰은 변경하지 않는다.
        return await self.renew()

    async def release(self) -> bool:
        return await self._eval(_RELEASE) == 1


async def enqueue_refresh(
    redis: ArqRedis,
    user_id: str,
    *,
    event_id: str,
    request_id: str | None = None,
    delivery_no: int | None = None,
) -> None:
    # ARQ의 완료 결과가 보존돼도 다른 보고서의 새 갱신을 막지 않는다.
    if request_id is None:
        await redis.enqueue_job(
            "profile_summary", user_id, _job_id=f"profile_summary:{user_id}:{event_id}"
        )
    else:
        await redis.enqueue_job(
            "profile_summary",
            user_id,
            request_id,
            delivery_no,
            _job_id=f"profile_summary:{user_id}:{event_id}",
        )
