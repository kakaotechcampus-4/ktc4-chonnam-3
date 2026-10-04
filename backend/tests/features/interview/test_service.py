"""POST /interviews 생성 서비스. spec/backend/features/interview.md "생성".

docs/testing.md Interview create / task-13
"""

import json
import uuid
from typing import Any

import pytest
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.models import AnalysisJob, InterviewSession, SessionRepository
from app.features.interview import queries, service
from app.shared.enums import Reason

from .factories import make_repo, make_run, make_user


class FakeRedis:
    """rt:{sessionId} 저장과 enqueue 호출만 기록한다. fail=True 면 RedisError."""

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.values: dict[str, tuple[str, int]] = {}
        self.jobs: list[tuple[str, tuple[Any, ...]]] = []

    async def set(self, key: str, value: str, ex: int) -> None:
        if self.fail:
            raise RedisError("down")
        self.values[key] = (value, ex)

    async def enqueue_job(self, name: str, *args: Any) -> None:
        self.jobs.append((name, args))


async def _create(db: AsyncSession, run: AnalysisJob, ids: list[uuid.UUID], redis: Any = None):
    return await service.create_interview(
        db, redis or FakeRedis(), user_id=run.user_id, run_id=run.id, repository_ids=ids
    )


async def test_create_ok(db: AsyncSession) -> None:
    run = await make_run(db, await make_user(db))
    repos = [await make_repo(db, run) for _ in range(2)]
    redis = FakeRedis()

    interview_id, session_id = await _create(db, run, [r.id for r in reversed(repos)], redis)

    interview = await db.get(InterviewSession, interview_id)
    assert interview is not None
    assert (interview.status, interview.job_posting_id) == ("preparing", run.job_posting_id)
    rows = await db.scalars(
        select(SessionRepository.repository_id)
        .where(SessionRepository.interview_session_id == interview_id)
        .order_by(SessionRepository.display_order)
    )
    assert list(rows) == [repos[1].id, repos[0].id]  # 요청 순서 유지
    value, ttl = redis.values[f"rt:{session_id}"]
    assert json.loads(value) == {"interviewId": str(interview_id), "userId": str(run.user_id)}
    assert ttl == service.REALTIME_SESSION_TTL_SECONDS
    assert redis.jobs == [("interview_prep", (str(interview_id),))]


@pytest.mark.parametrize(
    ("count", "duplicate", "reason"),
    [
        (0, False, Reason.NO_REPOSITORY_SELECTED),
        (6, False, Reason.TOO_MANY_REPOSITORIES),
        (2, True, Reason.INVALID_REPOSITORY),
    ],
)
async def test_create_rejects_repository_count(
    db: AsyncSession, count: int, duplicate: bool, reason: Reason
) -> None:
    run = await make_run(db, await make_user(db))
    ids = [(await make_repo(db, run)).id for _ in range(count)]
    if duplicate:
        ids[1] = ids[0]
    with pytest.raises(AppError) as exc:
        await _create(db, run, ids)
    assert exc.value.reason == reason


async def test_create_rejects_expired_run(db: AsyncSession) -> None:
    run = await make_run(db, await make_user(db), status="failed")
    repo = await make_repo(db, run)
    with pytest.raises(AppError) as exc:
        await _create(db, run, [repo.id])
    assert exc.value.reason == Reason.RUN_EXPIRED


async def test_create_rejects_unselectable_repository(db: AsyncSession) -> None:
    run = await make_run(db, await make_user(db))
    ok, bad = await make_repo(db, run), await make_repo(db, run, filter_status="excluded")
    with pytest.raises(AppError) as exc:
        await _create(db, run, [ok.id, bad.id])
    assert exc.value.reason == Reason.INVALID_REPOSITORY


async def test_create_rejects_second_active(db: AsyncSession) -> None:
    run = await make_run(db, await make_user(db))
    repo = await make_repo(db, run)
    await _create(db, run, [repo.id])
    with pytest.raises(AppError) as exc:
        await _create(db, run, [repo.id])
    assert exc.value.reason == Reason.SESSION_LIMIT_EXCEEDED


async def test_create_race_hits_unique_index(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """사전 조회를 통과한 동시 요청은 partial unique index 가 막는다."""
    run = await make_run(db, await make_user(db))
    repo = await make_repo(db, run)
    await _create(db, run, [repo.id])

    async def _no_active(*_: Any, **__: Any) -> bool:
        return False

    monkeypatch.setattr(queries, "has_active_interview", _no_active)
    with pytest.raises(AppError) as exc:
        await _create(db, run, [repo.id])
    assert exc.value.reason == Reason.SESSION_LIMIT_EXCEEDED


async def test_create_redis_failure_rolls_back(db: AsyncSession) -> None:
    run = await make_run(db, await make_user(db))
    repo = await make_repo(db, run)
    with pytest.raises(AppError) as exc:
        await _create(db, run, [repo.id], FakeRedis(fail=True))
    assert exc.value.reason == Reason.INTERNAL_ERROR
    assert await queries.has_active_interview(db, run_id=run.id) is False
