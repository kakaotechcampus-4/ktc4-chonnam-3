import hashlib
import secrets
from collections.abc import Awaitable
from typing import cast

from redis.asyncio import Redis

from app.core.errors import AppError

# Check browser binding and consume atomically; a mismatch must leave state usable.
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
        # The cookie gets a separate secret, so the state in the URL is insufficient.
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
