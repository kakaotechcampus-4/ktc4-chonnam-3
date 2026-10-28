"""GET /interviews/{id} 서비스 — 응답 조립과 sessionId 재사용·재발급. 실제 Redis 를 쓴다.

spec/backend/features/interview.md "준비 실패", docs/pipeline.md 4.4 / task-13
"""

import asyncio
import json
from datetime import UTC, datetime, timedelta

import pytest

from app.core.config import get_settings
from app.core.errors import AppError
from app.db.models import InterviewSession, InterviewTurn
from app.features.interview import service
from app.shared.enums import Reason

from .factories import make_repo, make_run, make_user

_LAST_ERROR = {
    "reason": "prep_failed",
    "code": "l2_failed",
    "step": "analyze_repo",
    "recoverable": True,
    "occurredAt": "2026-10-06T00:00:00Z",
}


@pytest.fixture
async def created(db, redis):
    run = await make_run(db, await make_user(db))
    repo = await make_repo(db, run)
    interview_id, session_id = await service.create_interview(
        db, redis, user_id=run.user_id, run_id=run.id, repository_ids=[repo.id]
    )
    return run, interview_id, session_id


async def _get(db, redis, run, interview_id):
    return await service.get_interview(db, redis, user_id=run.user_id, interview_id=interview_id)


async def test_reuses_live_session(db, redis, created) -> None:
    run, interview_id, session_id = created
    detail = await _get(db, redis, run, interview_id)
    assert detail.session_id == session_id
    assert detail.last_error is None


async def test_other_user_not_found(db, redis, created) -> None:
    _, interview_id, _ = created
    other = await make_user(db)
    with pytest.raises(AppError) as exc:
        await service.get_interview(db, redis, user_id=other.id, interview_id=interview_id)
    assert exc.value.reason == Reason.NOT_FOUND


@pytest.mark.parametrize("lost_reverse", [True, False])
async def test_reissues_lost_session(db, redis, created, lost_reverse: bool) -> None:
    """두 키 모두 만료됐거나, rt:{sessionId} 만 사라져 짝이 깨졌으면 새로 발급한다."""
    run, interview_id, old = created
    await redis.delete(f"rt:{old}")
    if lost_reverse:
        await redis.delete(f"rt:interview:{interview_id}")

    new = (await _get(db, redis, run, interview_id)).session_id

    assert new != old
    assert await redis.get(f"rt:interview:{interview_id}") == new.encode()
    assert json.loads(await redis.get(f"rt:{new}"))["interviewId"] == str(interview_id)


async def test_concurrent_reissue_shares_one_session(db, redis, created) -> None:
    """두 탭이 동시에 재발급해도 같은 sessionId 를 받고 진 쪽 rt 키는 남지 않는다."""
    run, interview_id, old = created
    await redis.delete(f"rt:{old}", f"rt:interview:{interview_id}")

    a, b = await asyncio.gather(
        *(
            service._current_session_id(redis, interview_id=interview_id, user_id=run.user_id)
            for _ in range(2)
        )
    )

    assert a == b
    assert sorted(await redis.keys("rt:*")) == sorted(
        [f"rt:{a}".encode(), f"rt:interview:{interview_id}".encode()]
    )


async def test_in_progress_turns_and_timer(db, redis, created) -> None:
    run, interview_id, _ = created
    interview = await db.get(InterviewSession, interview_id)
    assert interview is not None
    interview.status = "in_progress"
    interview.current_turn = 1
    interview.started_at = datetime.now(UTC) - timedelta(seconds=100)
    interview.last_error = _LAST_ERROR  # preparing_failed 가 아니면 내려주지 않는다
    db.add(
        InterviewTurn(
            interview_session_id=interview_id, turn_no=1, persona="hr_manager", question_text="Q1"
        )
    )
    await db.commit()

    detail = await _get(db, redis, run, interview_id)

    assert [t.model_dump() for t in detail.turns] == [
        {"turn": 1, "persona": "hr_manager", "question": "Q1", "answer": None}
    ]
    total = get_settings().interview_duration_seconds
    assert total - 105 <= detail.remaining_seconds <= total - 100
    assert detail.last_error is None


async def test_preparing_failed_last_error(db, redis, created) -> None:
    run, interview_id, _ = created
    interview = await db.get(InterviewSession, interview_id)
    assert interview is not None
    interview.status = "preparing_failed"
    interview.last_error = _LAST_ERROR
    await db.commit()

    detail = await _get(db, redis, run, interview_id)

    assert detail.last_error is not None
    assert detail.last_error.model_dump(mode="json") == _LAST_ERROR


@pytest.mark.parametrize(
    "broken",
    [
        {**_LAST_ERROR, "message": "extra"},
        {k: v for k, v in _LAST_ERROR.items() if k != "occurredAt"},
        {**_LAST_ERROR, "step": "repo_analyze"},
    ],
    ids=["extra_key", "missing_occurred_at", "unknown_step"],
)
async def test_malformed_last_error_does_not_break_get(db, redis, created, broken) -> None:
    run, interview_id, _ = created
    interview = await db.get(InterviewSession, interview_id)
    assert interview is not None
    interview.status = "preparing_failed"
    interview.last_error = broken
    await db.commit()

    detail = await _get(db, redis, run, interview_id)

    assert detail.status == "preparing_failed"
    assert detail.last_error is None
