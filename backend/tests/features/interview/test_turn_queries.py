"""턴 조회 쿼리.

task-15
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.interview import queries

from .factories import make_interview, make_repo, make_run, make_turn, make_user


async def test_list_turns_ordered_and_scoped(db: AsyncSession) -> None:
    run = await make_run(db, await make_user(db))
    repo = await make_repo(db, run)
    interview = await make_interview(db, run, [repo])
    other = await make_interview(db, run, [repo], status="completed")
    await make_turn(db, interview, 2)
    await make_turn(db, interview, 1, answered=True)
    await make_turn(db, other, 1)

    turns = await queries.list_turns(db, interview_id=interview.id)

    assert [(t.turn_no, t.status) for t in turns] == [(1, "answered"), (2, "asked")]


async def test_list_turns_empty(db: AsyncSession) -> None:
    run = await make_run(db, await make_user(db))
    interview = await make_interview(db, run, [await make_repo(db, run)])
    assert await queries.list_turns(db, interview_id=interview.id) == []
