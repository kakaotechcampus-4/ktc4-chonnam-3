"""턴 저장 동시 호출. 요청마다 별도 DB 연결(세션)로 같은 면접에 동시에 쓴다.

조건부 UPDATE 가 행 락에서 한쪽만 통과시키는지 확인한다 (PR #65 리뷰 3, #66 리뷰 ④).
task-15
"""

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import InterviewSession, InterviewTurn
from app.features.interview.turn_service import (
    TurnRejected,
    complete_interview,
    save_answer,
    save_question,
)

from .factories import make_interview, make_repo, make_run, make_turn, make_user


async def _committed_interview(db: AsyncSession, **overrides: Any) -> uuid.UUID:
    run = await make_run(db, await make_user(db))
    interview = await make_interview(db, run, [await make_repo(db, run)], **overrides)
    if overrides.get("current_turn"):
        await make_turn(db, interview, overrides["current_turn"], answered=True)
    await db.commit()
    return interview.id


async def _race[T](app: FastAPI, call: Callable[[AsyncSession], Awaitable[T]]) -> list[T]:
    """같은 호출을 연결 2개에서 동시에 실행한다."""

    async def one() -> T:
        async with app.state.session_factory() as session:
            return await call(session)

    return list(await asyncio.gather(one(), one()))


async def test_concurrent_questions_save_one_turn(app: FastAPI, db: AsyncSession) -> None:
    interview_id = await _committed_interview(db)

    results = await _race(
        app,
        lambda s: save_question(
            s, interview_id=interview_id, persona="hr_manager", question_text="자기소개"
        ),
    )

    assert sum(isinstance(r, InterviewTurn) for r in results) == 1
    assert TurnRejected.PREVIOUS_UNANSWERED in results
    count = await db.scalar(
        select(func.count()).where(InterviewTurn.interview_session_id == interview_id)
    )
    current_turn = await db.scalar(
        select(InterviewSession.current_turn).where(InterviewSession.id == interview_id)
    )
    assert (count, current_turn) == (1, 1)


async def test_concurrent_answers_keep_one(app: FastAPI, db: AsyncSession) -> None:
    interview_id = await _committed_interview(db)
    await save_question(db, interview_id=interview_id, persona="hr_manager", question_text="q")

    results = await _race(
        app, lambda s: save_answer(s, interview_id=interview_id, turn_no=1, answer_text="답변")
    )

    assert sorted(results, key=str) == [None, TurnRejected.ALREADY_ANSWERED]


async def test_concurrent_complete_once(app: FastAPI, db: AsyncSession) -> None:
    interview_id = await _committed_interview(db, current_turn=9)

    results = await _race(app, lambda s: complete_interview(s, interview_id=interview_id))

    assert sorted(results) == [False, True]
    status = await db.scalar(
        select(InterviewSession.status).where(InterviewSession.id == interview_id)
    )
    assert status == "completed"
