"""POST /interviews/{id}/prepare/retry 서비스. 실제 PostgreSQL·Redis 를 쓴다.

spec/backend/features/interview.md "준비 실패" / task-13
"""

import uuid
from typing import Any

import pytest
from redis.exceptions import RedisError

from app.core.errors import AppError
from app.db.models import InterviewSession
from app.features.interview import service
from app.shared.enums import Reason

from .factories import make_repo, make_run, make_user


@pytest.fixture
async def failed(db, redis):
    """recoverable 준비 실패 면접 1개. (run, repo, interview_id)."""
    run = await make_run(db, await make_user(db))
    repo = await make_repo(db, run)
    interview_id, _ = await service.create_interview(
        db, redis, user_id=run.user_id, run_id=run.id, repository_ids=[repo.id]
    )
    await _set(db, interview_id, status="preparing_failed", last_error={"recoverable": True})
    return run, repo, interview_id


async def _set(db, interview_id: uuid.UUID, **fields: Any) -> None:
    interview = await db.get(InterviewSession, interview_id)
    for key, value in fields.items():
        setattr(interview, key, value)
    await db.commit()


async def _status(db, interview_id: uuid.UUID) -> str:
    interview = await db.get(InterviewSession, interview_id)
    await db.refresh(interview)
    return interview.status


async def _retry(db, redis, run, interview_id) -> None:
    await service.retry_prepare(db, redis, user_id=run.user_id, interview_id=interview_id)


async def test_retry_ok(db, redis, failed) -> None:
    run, _, interview_id = failed
    queued = await redis.zcard("arq:queue")

    await _retry(db, redis, run, interview_id)

    assert await _status(db, interview_id) == "preparing"
    assert await redis.zcard("arq:queue") == queued + 1


@pytest.mark.parametrize(
    ("fields", "reason"),
    [
        ({"status": "preparing"}, Reason.PREP_IN_PROGRESS),
        ({"status": "completed"}, Reason.PREP_FAILED),
        ({"last_error": {"recoverable": False}}, Reason.PREP_FAILED),
    ],
)
async def test_retry_rejected(db, redis, failed, fields, reason) -> None:
    run, _, interview_id = failed
    await _set(db, interview_id, **fields)
    with pytest.raises(AppError) as exc:
        await _retry(db, redis, run, interview_id)
    assert exc.value.reason == reason


async def test_retry_blocked_by_newer_active_interview(db, redis, failed) -> None:
    """실패 뒤 같은 run 으로 새 면접을 만들었으면 옛 면접은 재시도할 수 없다."""
    run, repo, interview_id = failed
    await service.create_interview(
        db, redis, user_id=run.user_id, run_id=run.id, repository_ids=[repo.id]
    )
    with pytest.raises(AppError) as exc:
        await _retry(db, redis, run, interview_id)
    assert exc.value.reason == Reason.PREP_FAILED
    assert await _status(db, interview_id) == "preparing_failed"


async def test_retry_other_user_session_expired(db, redis, failed) -> None:
    _, _, interview_id = failed
    other = await make_user(db)
    with pytest.raises(AppError) as exc:
        await service.retry_prepare(db, redis, user_id=other.id, interview_id=interview_id)
    assert exc.value.reason == Reason.SESSION_EXPIRED


async def test_retry_enqueue_failure_restores_failed(db, failed) -> None:
    run, _, interview_id = failed

    class DownRedis:
        async def enqueue_job(self, *_: Any) -> None:
            raise RedisError("down")

    with pytest.raises(AppError) as exc:
        await _retry(db, DownRedis(), run, interview_id)
    assert exc.value.reason == Reason.INTERNAL_ERROR
    assert await _status(db, interview_id) == "preparing_failed"
