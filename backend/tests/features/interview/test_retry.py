"""POST /interviews/{id}/retry 재도전 서비스. 실제 PostgreSQL·Redis 를 쓴다.

spec/backend/features/interview.md "/interviews/{id}/retry" / task-13
"""

import pytest

from app.core.errors import AppError
from app.db.models import InterviewSession, Repository
from app.features.interview import queries, service
from app.shared.enums import Reason

from .factories import make_repo, make_run, make_user


@pytest.fixture
async def finished(db, redis):
    """completed 원본 면접. (run, repos, interview_id)."""
    run = await make_run(db, await make_user(db))
    repos = [await make_repo(db, run) for _ in range(2)]
    interview_id, _ = await service.create_interview(
        db,
        redis,
        user_id=run.user_id,
        run_id=run.id,
        repository_ids=[r.id for r in reversed(repos)],
    )
    await _set_status(db, interview_id, "completed")
    return run, repos, interview_id


async def _set_status(db, interview_id, status: str) -> None:
    interview = await db.get(InterviewSession, interview_id)
    interview.status = status
    await db.commit()


async def _retry(db, redis, run, interview_id):
    return await service.retry_interview(db, redis, user_id=run.user_id, interview_id=interview_id)


@pytest.mark.parametrize("status", ["completed", "abandoned"])
async def test_retry_copies_original(db, redis, finished, status: str) -> None:
    run, repos, original_id = finished
    await _set_status(db, original_id, status)

    new_id, session_id = await _retry(db, redis, run, original_id)

    new = await db.get(InterviewSession, new_id)
    assert new is not None
    assert (new.status, new.analysis_job_id, new.retry_of_interview_id) == (
        "preparing",
        run.id,
        original_id,
    )
    # 원본 선택 순서 그대로
    assert await queries.list_repository_ids(db, interview_id=new_id) == [repos[1].id, repos[0].id]
    assert await redis.get(f"rt:interview:{new_id}") == session_id.encode()


@pytest.mark.parametrize("status", ["preparing", "preparing_failed", "in_progress"])
async def test_retry_rejects_unfinished(db, redis, finished, status: str) -> None:
    run, _, original_id = finished
    await _set_status(db, original_id, status)
    with pytest.raises(AppError) as exc:
        await _retry(db, redis, run, original_id)
    assert exc.value.reason == Reason.ORIGINAL_NOT_COMPLETED


@pytest.mark.parametrize("change", ["private", "deleted"])
async def test_retry_repository_unavailable(db, redis, finished, change: str) -> None:
    run, repos, original_id = finished
    for repo in repos:
        if change == "private":
            repo.is_private = True
        else:
            await db.delete(await db.get(Repository, repo.id))
    await db.commit()
    with pytest.raises(AppError) as exc:
        await _retry(db, redis, run, original_id)
    assert exc.value.reason == Reason.REPOSITORY_UNAVAILABLE


async def test_retry_other_user_not_found(db, redis, finished) -> None:
    _, _, original_id = finished
    other = await make_user(db)
    with pytest.raises(AppError) as exc:
        await service.retry_interview(db, redis, user_id=other.id, interview_id=original_id)
    assert exc.value.reason == Reason.NOT_FOUND


async def test_retry_session_limit(db, redis, finished) -> None:
    """같은 run 에 활성 면접이 있으면 생성과 같은 409."""
    run, _, original_id = finished
    await _retry(db, redis, run, original_id)
    with pytest.raises(AppError) as exc:
        await _retry(db, redis, run, original_id)
    assert exc.value.reason == Reason.SESSION_LIMIT_EXCEEDED
