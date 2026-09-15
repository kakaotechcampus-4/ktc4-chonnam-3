"""Redis 로그인 세션 (auth:sess:{sid}, 14d 슬라이딩).

docs/redis-keys.md / task-06

DEVON JWT 전달 방식은 PENDING_FE 다. 확정 전까지 인증 주체는 이 Redis 세션이며,
OAuth 흐름(task-06)이 들어오면 issue_session 만 호출하면 된다.
"""

import uuid

from app.core.config import get_settings
from app.realtime.bus import get_redis

SESSION_KEY = "auth:sess:{sid}"


async def issue_session(user_id: uuid.UUID) -> str:
    """세션 id 를 발급하고 user_id 를 매핑한다."""
    sid = uuid.uuid4().hex
    settings = get_settings()
    await get_redis().set(
        SESSION_KEY.format(sid=sid), str(user_id), ex=settings.session_ttl_seconds
    )
    return sid


async def resolve_session(sid: str) -> uuid.UUID | None:
    """세션 id -> user_id. 접근할 때마다 TTL 을 슬라이딩한다."""
    redis = get_redis()
    key = SESSION_KEY.format(sid=sid)
    raw = await redis.get(key)
    if raw is None:
        return None
    await redis.expire(key, get_settings().session_ttl_seconds)
    try:
        return uuid.UUID(raw)
    except ValueError:
        return None


async def revoke_session(sid: str) -> None:
    """로그아웃."""
    await get_redis().delete(SESSION_KEY.format(sid=sid))
