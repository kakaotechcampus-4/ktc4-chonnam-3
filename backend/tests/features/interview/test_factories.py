"""턴 목데이터가 DB 제약(CHECK·UNIQUE·FK)을 통과하는지 확인한다.

task-15
"""

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from tests.features.interview.factories import (
    make_evidence,
    make_interview,
    make_repo,
    make_run,
    make_turn,
    make_user,
)


async def test_interview_with_turns(db: AsyncSession) -> None:
    run = await make_run(db, await make_user(db))
    repos = [await make_repo(db, run), await make_repo(db, run)]
    interview = await make_interview(db, run, repos)
    evidence = await make_evidence(db, interview, repos[0])
    first = await make_turn(db, interview, 1, answered=True)
    second = await make_turn(db, interview, 2, persona="tech_lead")

    assert interview.status == "in_progress"
    assert evidence.tool_name is None
    assert (first.status, first.answer_text) == ("answered", "답변 1")
    assert (second.status, second.answer_text) == ("asked", None)


async def test_duplicate_turn_no_rejected(db: AsyncSession) -> None:
    run = await make_run(db, await make_user(db))
    interview = await make_interview(db, run, [await make_repo(db, run)])
    await make_turn(db, interview, 1)
    with pytest.raises(IntegrityError):
        await make_turn(db, interview, 1)
