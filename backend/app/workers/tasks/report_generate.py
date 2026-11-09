"""report 조회가 enqueue 하는 lazy 생성 태스크. 인자는 interviewId 뿐이다.

features/report 로직을 호출하고 성공 뒤 profile_summary 를 enqueue 한다.
면접 종료만으로 자동 생성하지 않으며 자동 재시도도 없다(max_tries=1).
명시 요청은 영구 실행권을 검사하고 승인된 재평가만 새 리포트 버전을 만든다.
실패하면 실패 코드를 Redis 에 남기고 report:gen lock 은 풀지 않는다. 실패 이력이 409 판정에
연결되기 전까지 lock TTL(5분)이 냉각 시간이라 폴링마다 생성이 재시도되지 않는다.
성공·skipped·exists 일 때만 lock 을 푼다.

docs/layer-rules.md 1절 / task-16
"""

import asyncio
import uuid
from contextlib import suppress
from typing import Any

from redis.exceptions import RedisError

from app.core.config import get_settings
from app.core.logging import get_logger
from app.features.report import generation, service
from app.workers.profile_refresh_queue import enqueue_refresh

logger = get_logger(__name__)


async def report_generate(
    ctx: dict[str, Any], interview_id: str, request_id: str | None = None
) -> None:
    iid = uuid.UUID(interview_id)
    redis = ctx["redis"]
    identity = await generation.claim(
        ctx["session_factory"], iid, uuid.UUID(request_id) if request_id else None
    )
    if identity is None:
        if request_id is None:
            with suppress(RedisError):
                await generation.release(redis, iid, "1")
        return
    owner: str | None = None
    failed = False
    try:
        # DB 실행권을 얻은 뒤의 Redis·설정 오류도 같은 실패 정리 경계를 거친다.
        raw_owner = await redis.get(f"report:gen:{iid}")
        owner = raw_owner.decode() if isinstance(raw_owner, bytes) else raw_owner
        if owner is None:
            if not await redis.set(
                f"report:gen:{iid}", str(identity), nx=True, ex=service.REPORT_LOCK_TTL_SECONDS
            ):
                await generation.fail(ctx["session_factory"], identity, "generation_owner_changed")
                return
            owner = str(identity)
        if owner not in {"1", str(identity)}:
            owner = None
            await generation.fail(ctx["session_factory"], identity, "generation_owner_changed")
            return
        outcome = await service.generate_report(
            ctx["session_factory"],
            interview_id=iid,
            llm=get_settings().require_llm(),
            http_client=ctx["http_client"],
            generation_request_id=identity,
        )
        if outcome in {"created", "revised"}:
            await _enqueue_profile_summary(
                ctx, iid, event_id=str(identity) if outcome == "revised" else None
            )
    except asyncio.CancelledError:
        failed = True
        await asyncio.shield(generation.fail(ctx["session_factory"], identity, "worker_cancelled"))
        with suppress(RedisError):
            await asyncio.shield(
                generation.release(redis, iid, owner or str(identity), "worker_cancelled")
            )
        raise
    except Exception as error:
        failed = True
        code = "queue_unavailable" if isinstance(error, RedisError) else service.failure_code(error)
        logger.warning("report_generate_failed", interview_id=interview_id, error_code=code)
        await generation.fail(ctx["session_factory"], identity, code)
        with suppress(RedisError):
            await generation.release(redis, iid, owner or str(identity), code)
    finally:
        if not failed and owner is not None:
            with suppress(RedisError):
                await generation.release(redis, iid, owner)


async def _enqueue_profile_summary(
    ctx: dict[str, Any], interview_id: uuid.UUID, *, event_id: str | None = None
) -> None:
    """성공본은 유지하고 기존 user-only 프로필 작업을 전달한다.

    영속 outbox 생산자와 3인수 worker·reaper는 후속 묶음을 적용할 때 함께 활성화한다.
    """
    try:
        async with ctx["session_factory"]() as db:
            user_id = await service.get_interview_user_id(db, interview_id)
        await enqueue_refresh(ctx["redis"], str(user_id), event_id=event_id or str(interview_id))
    except Exception:
        logger.error("profile_summary_enqueue_failed", interview_id=str(interview_id))
