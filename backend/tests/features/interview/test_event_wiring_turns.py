"""turn_asked / turn_answered / interview_completed 이벤트 연결. task-17"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.interview.turn_service import complete_interview, save_answer, save_question
from tests.event_helpers import broken_events as broken_events
from tests.event_helpers import names

from .factories import make_interview, make_repo, make_run, make_turn, make_user


async def _in_progress(db: AsyncSession, **overrides):
    run = await make_run(db, await make_user(db))
    repo = await make_repo(db, run)
    return await make_interview(db, run, [repo], **overrides)


async def _ask(db: AsyncSession, interview_id):
    return await save_question(
        db, interview_id=interview_id, persona="hr_manager", question_text="자기소개"
    )


async def test_turn_asked_recorded_once_and_not_for_rejected_question(db: AsyncSession) -> None:
    interview = await _in_progress(db)

    await _ask(db, interview.id)
    await _ask(db, interview.id)  # 이전 턴 미답변으로 거부된다

    assert await names(db) == ["turn_asked"]


async def test_turn_answered_recorded_once_even_when_answer_is_resent(db: AsyncSession) -> None:
    interview = await _in_progress(db)
    await _ask(db, interview.id)

    await save_answer(db, interview_id=interview.id, turn_no=1, answer_text="답")
    await save_answer(db, interview_id=interview.id, turn_no=1, answer_text="답")

    assert await names(db) == ["turn_asked", "turn_answered"]


async def test_interview_completed_recorded_once_even_when_called_twice(db: AsyncSession) -> None:
    interview = await _in_progress(db, current_turn=9)
    await make_turn(db, interview, 9, answered=True)
    await db.commit()

    assert await complete_interview(db, interview_id=interview.id) is True
    assert await complete_interview(db, interview_id=interview.id) is False

    assert await names(db) == ["interview_completed"]


async def test_turn_event_failure_does_not_block_turn_flow(db: AsyncSession, broken_events) -> None:
    interview = await _in_progress(db, total_turns=1)

    assert not isinstance(await _ask(db, interview.id), Exception)
    assert await save_answer(db, interview_id=interview.id, turn_no=1, answer_text="답") is None
    assert await complete_interview(db, interview_id=interview.id) is True

    assert await names(db) == []
