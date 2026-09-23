"""Opaque Redis sessions. Expiry updates never recreate a deleted session."""

import re
import secrets
from uuid import UUID

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.errors import AppError, Reason

_SESSION_ID = re.compile(r"[A-Za-z0-9_-]{43}")


class SessionStore:
    def __init__(self, redis: Redis, ttl_seconds: int) -> None:
        self.redis = redis
        self.ttl_seconds = ttl_seconds

    async def create(self, user_id: UUID) -> str:
        try:
            while True:
                sid = secrets.token_urlsafe(32)
                if await self.redis.set(
                    f"auth:sess:{sid}", str(user_id), ex=self.ttl_seconds, nx=True
                ):
                    return sid
        except RedisError:
            raise AppError(Reason.INTERNAL_ERROR) from None

    async def get(self, sid: str | None) -> UUID | None:
        if sid is None or not _SESSION_ID.fullmatch(sid):
            return None
        try:
            value = await self.redis.get(f"auth:sess:{sid}")
        except RedisError:
            raise AppError(Reason.INTERNAL_ERROR) from None
        if value is None:
            return None
        try:
            return UUID(value.decode() if isinstance(value, bytes) else value)
        except (ValueError, UnicodeDecodeError):
            return None

    async def touch(self, sid: str) -> bool:
        if not _SESSION_ID.fullmatch(sid):
            return False
        try:
            # EXPIRE는 없는 키를 만들지 않아 동시 로그아웃으로 삭제된 세션이 되살아나지 않는다.
            return bool(await self.redis.expire(f"auth:sess:{sid}", self.ttl_seconds))
        except RedisError:
            raise AppError(Reason.INTERNAL_ERROR) from None

    async def delete(self, sid: str | None) -> None:
        if sid is None or not _SESSION_ID.fullmatch(sid):
            return
        try:
            await self.redis.delete(f"auth:sess:{sid}")
        except RedisError:
            raise AppError(Reason.INTERNAL_ERROR) from None
