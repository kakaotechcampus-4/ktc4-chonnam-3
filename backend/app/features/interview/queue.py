"""면접 준비 job 등록. DB의 preparing 행이 복구 근거이므로 등록 실패는 reaper가 이어받는다."""

from uuid import UUID

from arq.connections import ArqRedis

from app.core.logging import get_logger
from app.features.analysis.queue import enqueue_once

logger = get_logger(__name__)


async def enqueue_interview_prep(redis: ArqRedis, interview_id: UUID) -> bool:
    try:
        return await enqueue_once(
            redis, "interview_prep", f"interview_prep:{interview_id}", str(interview_id)
        )
    except Exception:
        # 면접 행은 이미 commit 됐다. 외부 오류 본문 없이 복구 필요 사실만 남긴다.
        logger.warning("interview_prep_enqueue_pending", interview_id=str(interview_id))
        return False
