"""report 조회가 enqueue 하는 lazy 생성 태스크. 인자는 interviewId 뿐이다.

features/report 로직을 호출하고 성공 뒤 profile_summary 를 enqueue 한다.
면접 종료만으로 자동 생성하지 않으며 자동 재시도도 없다(max_tries=1).
재생성·수동 재시도는 Sprint 2다.
실패하면 실패 코드를 Redis 에 남기고 어떤 결과든 마지막에 report:gen lock 을 푼다.

docs/layer-rules.md 1절 / task-16
"""

import uuid
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger
from app.features.report import service

logger = get_logger(__name__)


async def report_generate(ctx: dict[str, Any], interview_id: str) -> None:
    iid = uuid.UUID(interview_id)
    redis = ctx["redis"]
    try:
        outcome = await service.generate_report(
            ctx["session_factory"],
            interview_id=iid,
            llm=get_settings().require_llm(),
            http_client=ctx["http_client"],
        )
        if outcome == "created":
            await _enqueue_profile_summary(ctx, iid)
    except Exception as error:
        code = service.failure_code(error)
        logger.warning("report_generate_failed", interview_id=interview_id, error_code=code)
        await service.record_failure(redis, iid, code)
    finally:
        await service.release_lock(redis, iid)


async def _enqueue_profile_summary(ctx: dict[str, Any], interview_id: uuid.UUID) -> None:
    """성공한 report 를 되돌리지 않도록 enqueue 실패는 로그만 남긴다.

    같은 사용자의 진행 중 job 은 _job_id 로 중복 enqueue 를 막는다.
    """
    try:
        async with ctx["session_factory"]() as db:
            user_id = await service.get_interview_user_id(db, interview_id)
        await ctx["redis"].enqueue_job(
            "profile_summary", str(user_id), _job_id=f"profile_summary:{user_id}"
        )
    except Exception:
        logger.error("profile_summary_enqueue_failed", interview_id=str(interview_id))
