"""POST /interviews/{id}/prepare/retry 서비스. 실제 PostgreSQL·Redis 를 쓴다.

spec/backend/features/interview.md "준비 실패" / task-13
"""

import logging
import uuid
from typing import Any

import pytest
from redis.exceptions import RedisError
from sqlalchemy.exc import OperationalError

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
    assert exc.value.reason == Reason.SESSION_LIMIT_EXCEEDED
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


async def test_retry_enqueue_failure_restore_failure_is_logged(
    db, failed, monkeypatch, caplog
) -> None:
    """복구 UPDATE 까지 실패해도 로그를 남기고 500 으로 응답한다."""
    run, _, interview_id = failed

    class DownRedis:
        async def enqueue_job(self, *_: Any) -> None:
            raise RedisError("down")

    original = db.execute
    calls = 0

    async def flaky_execute(*args: Any, **kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        if calls > 1:  # 1번째는 소유 조회, 2번째가 복구 UPDATE
            raise OperationalError("update", {}, Exception("db down"))
        return await original(*args, **kwargs)

    monkeypatch.setattr(db, "execute", flaky_execute)
    caplog.set_level(logging.ERROR)
    with pytest.raises(AppError) as exc:
        await _retry(db, DownRedis(), run, interview_id)
    assert exc.value.reason == Reason.INTERNAL_ERROR
    assert "interview_prepare_retry_rollback_failed" in caplog.text
