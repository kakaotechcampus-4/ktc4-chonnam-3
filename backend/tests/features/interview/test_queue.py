"""interview_prep 등록은 결정적 _job_id 로 중복 실행을 막는다. 실제 ARQ·Redis 로 검증한다."""

import uuid
from typing import Any

from arq.jobs import Job, JobStatus
from redis.exceptions import RedisError

from app.features.interview.queue import enqueue_interview_prep


async def test_enqueue_registers_zero_payload_job_with_deterministic_id(redis) -> None:
    interview_id = uuid.uuid4()
    assert await enqueue_interview_prep(redis, interview_id) is True
    job = Job(f"interview_prep:{interview_id}", redis)
    assert await job.status() == JobStatus.queued
    info = await job.info()
    assert info is not None
    assert info.function == "interview_prep" and info.args == (str(interview_id),)


async def test_duplicate_enqueue_keeps_single_queued_job(redis) -> None:
    interview_id = uuid.uuid4()
    assert await enqueue_interview_prep(redis, interview_id) is True
    assert await enqueue_interview_prep(redis, interview_id) is True
    assert await redis.zcard(redis.default_queue_name) == 1


async def test_enqueue_failure_is_reported_not_raised() -> None:
    class DownRedis:
        async def enqueue_job(self, *_: Any, **__: Any) -> None:
            raise RedisError("down")

    assert await enqueue_interview_prep(DownRedis(), uuid.uuid4()) is False  # type: ignore[arg-type]
