"""report_generate 성공 뒤 enqueue 되는 프로필 갱신 태스크. 인자는 userId 뿐이다.

profile:gen:{userId} lock(NX, 10분)을 잡은 job 만 집계한다. 이미 있으면 바로 끝낸다.
실패해도 예외를 밖으로 내지 않고 코드만 로그에 남긴다. 이전 성공 요약은 그대로이며
이미 성공한 report 에는 영향이 없다. 자동 재시도(max_tries=1)·복구는 Sprint 2다.

docs/layer-rules.md 1절 / task-16
"""

import uuid
from typing import Any

from redis.exceptions import RedisError

from app.core.config import get_settings
from app.core.logging import get_logger
from app.features.profile import service

logger = get_logger(__name__)


async def profile_summary(ctx: dict[str, Any], user_id: str) -> None:
    uid = uuid.UUID(user_id)
    redis = ctx["redis"]
    key = service.PROFILE_LOCK_KEY.format(user_id=uid)
    try:
        acquired = await redis.set(key, "1", nx=True, ex=service.PROFILE_LOCK_TTL_SECONDS)
    except RedisError:
        logger.error("profile_summary_lock_failed", user_id=user_id)
        return
    if not acquired:
        return
    try:
        outcome = await service.refresh_profile_summary(
            ctx["session_factory"],
            user_id=uid,
            llm=get_settings().require_llm(),
            http_client=ctx["http_client"],
        )
        logger.info("profile_summary_done", user_id=user_id, outcome=outcome)
    except Exception as error:
        logger.warning(
            "profile_summary_failed", user_id=user_id, error_code=service.failure_code(error)
        )
    finally:
        try:
            await redis.delete(key)
        except RedisError:
            logger.error("profile_summary_lock_release_failed", user_id=user_id)
