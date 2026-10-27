"""DB가 확정한 작업을 ARQ에 등록한다. 등록 실패는 queued 복구 대상이다."""

from uuid import UUID

from arq.connections import ArqRedis
from arq.constants import (
    in_progress_key_prefix,
    job_key_prefix,
    result_key_prefix,
    retry_key_prefix,
)
from arq.jobs import Job, JobStatus

from app.core.logging import get_logger

logger = get_logger(__name__)

# 큐·실행 표식이 없는 잔여 payload/result만 원자적으로 지운다.
# 상태 조회와 삭제 사이 다른 reaper가 등록한 정상 작업을 삭제하지 않도록 한다.
_CLEAR_RESIDUE = """
if redis.call('EXISTS', KEYS[1]) == 1 or redis.call('ZSCORE', KEYS[2], ARGV[1]) then
    return 0
end
return redis.call('DEL', KEYS[3], KEYS[4], KEYS[5])
"""


async def enqueue_analysis(redis: ArqRedis, run_id: UUID, page: int | None = None) -> bool:
    function = "analysis_run" if page is None else "candidate_page_analyze"
    identity = f"{function}:{run_id}" + (f":{page}" if page is not None else "")
    arguments = (str(run_id),) if page is None else (str(run_id), page)
    try:
        job = await redis.enqueue_job(function, *arguments, _job_id=identity)
        if job is None:
            state = await Job(identity, redis).status()
            if state in {JobStatus.not_found, JobStatus.complete}:
                await redis.eval(  # type: ignore[misc]  # redis-py의 동기·비동기 공용 반환 타입
                    _CLEAR_RESIDUE,
                    5,
                    in_progress_key_prefix + identity,
                    redis.default_queue_name,
                    job_key_prefix + identity,
                    result_key_prefix + identity,
                    retry_key_prefix + identity,
                    identity,
                )
                await redis.enqueue_job(function, *arguments, _job_id=identity)
                state = await Job(identity, redis).status()
            return state in {JobStatus.queued, JobStatus.deferred, JobStatus.in_progress}
        return True
    except Exception:
        # DB 저장은 성공했다. 외부 오류의 본문·토큰 없이 복구 필요 사실만 남긴다.
        logger.warning("analysis_enqueue_pending", run_id=str(run_id), page=page)
        return False
