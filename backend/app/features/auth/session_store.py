import hashlib
import secrets
from collections.abc import Awaitable
from typing import cast

from redis.asyncio import Redis

from app.core.errors import AppError

# 브라우저 연결 확인과 state 소모를 원자적으로 처리하고, 불일치 시에는 state를 남겨 둔다.
CONSUME_STATE = """
if redis.call('HGET', KEYS[1], 'binding') ~= ARGV[1] then return false end
local verifier = redis.call('HGET', KEYS[1], 'verifier')
redis.call('DEL', KEYS[1])
return verifier
"""


class OAuthStateStore:
    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    async def start_state(self) -> tuple[str, str, str]:
        # 쿠키에 별도의 비밀값을 두어 URL의 state만으로는 인증을 완료할 수 없게 한다.
        state, binding, verifier = (secrets.token_urlsafe(32) for _ in range(3))
        async with self.redis.pipeline(transaction=True) as pipeline:
            pipeline.hset(
                f"auth:oauth:{state}",
                mapping={
                    "binding": hashlib.sha256(binding.encode()).hexdigest(),
                    "verifier": verifier,
                },
            )
            pipeline.expire(f"auth:oauth:{state}", 600)
            await pipeline.execute()
        return state, binding, verifier

    async def consume_state(self, state: str | None, binding: str | None) -> str:
        if not state or not binding or len(state) > 128 or len(binding) > 128:
            raise AppError("invalid_state", 400)
        verifier = await cast(
            Awaitable[object],
            self.redis.eval(
                CONSUME_STATE,
                1,
                f"auth:oauth:{state}",
                hashlib.sha256(binding.encode()).hexdigest(),
            ),
        )
        if not isinstance(verifier, str):
            raise AppError("invalid_state", 400)
        return verifier
