"""턴 저장 service. Director 출력은 인자 고정값으로 대신한다.

task-15
"""

import uuid
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import InterviewSession, InterviewTurn, TurnEvidence
from app.features.interview.turn_service import TurnRejected, save_answer, save_question

from .factories import make_evidence, make_interview, make_repo, make_run, make_turn, make_user


async def _setup(db: AsyncSession, **overrides: Any) -> tuple[InterviewSession, Any]:
    run = await make_run(db, await make_user(db))
    repo = await make_repo(db, run)
    return await make_interview(db, run, [repo], **overrides), repo


async def _ask(
    db: AsyncSession, interview_id: uuid.UUID, **kw: Any
) -> InterviewTurn | TurnRejected:
    return await save_question(
        db, interview_id=interview_id, persona="hr_manager", question_text="자기소개", **kw
    )


async def test_first_question_without_evidence(db: AsyncSession) -> None:
    interview, _ = await _setup(db)

    turn = await _ask(db, interview.id)

    assert isinstance(turn, InterviewTurn)
    assert (turn.turn_no, turn.status, turn.persona) == (1, "asked", "hr_manager")
    await db.refresh(interview)
    assert interview.current_turn == 1
    assert await db.scalar(select(TurnEvidence).where(TurnEvidence.turn_id == turn.id)) is None


async def test_question_links_evidence(db: AsyncSession) -> None:
    interview, repo = await _setup(db)
    evidences = [await make_evidence(db, interview, repo) for _ in range(2)]

    turn = await _ask(db, interview.id, evidence_ids=[e.id for e in evidences])

    assert isinstance(turn, InterviewTurn)
    rows = (await db.scalars(select(TurnEvidence).where(TurnEvidence.turn_id == turn.id))).all()
    assert {r.evidence_id for r in rows} == {e.id for e in evidences}
    assert {r.usage for r in rows} == {"question_basis"}


async def test_next_question_after_answer(db: AsyncSession) -> None:
    interview, _ = await _setup(db, current_turn=1)
    await make_turn(db, interview, 1, answered=True)

    turn = await _ask(db, interview.id, depth=2, parent_turn_no=1)

    assert isinstance(turn, InterviewTurn)
    assert (turn.turn_no, turn.depth, turn.parent_turn_no) == (2, 2, 1)


@pytest.mark.parametrize(
    ("overrides", "last_answered", "reason"),
    [
        ({"current_turn": 1}, False, TurnRejected.PREVIOUS_UNANSWERED),
        ({"current_turn": 9}, True, TurnRejected.TURNS_EXHAUSTED),
        ({"status": "completed"}, None, TurnRejected.NOT_IN_PROGRESS),
    ],
)
async def test_question_blocked(
    db: AsyncSession,
    overrides: dict[str, Any],
    last_answered: bool | None,
    reason: TurnRejected,
) -> None:
    interview, _ = await _setup(db, **overrides)
    if last_answered is not None:
        await make_turn(db, interview, overrides["current_turn"], answered=last_answered)

    assert await _ask(db, interview.id) == reason


async def test_foreign_evidence_rejected(db: AsyncSession) -> None:
    interview, repo = await _setup(db)
    other, _ = await _setup(db)
    foreign = await make_evidence(db, other, repo)
    # 실제 흐름처럼 면접은 이미 commit 된 상태 — service rollback 이 목데이터까지 지우지 않게.
    await db.commit()

    with pytest.raises(ValueError):
        await _ask(db, interview.id, evidence_ids=[foreign.id])

    assert await db.scalar(select(InterviewTurn)) is None
    await db.refresh(interview)
    assert interview.current_turn == 0


async def test_unknown_persona_rejected_before_update(db: AsyncSession) -> None:
    """허용 밖 persona 는 턴 번호를 올리기 전에 막는다 — DB CHECK 오류로 늦게 터지지 않게."""
    interview, _ = await _setup(db)

    with pytest.raises(ValueError):
        await save_question(db, interview_id=interview.id, persona="ceo", question_text="Q")

    assert await db.scalar(select(InterviewTurn)) is None
    await db.refresh(interview)
    assert interview.current_turn == 0


async def _answer(
    db: AsyncSession, interview_id: uuid.UUID, turn_no: int, text: str
) -> TurnRejected | None:
    return await save_answer(db, interview_id=interview_id, turn_no=turn_no, answer_text=text)


async def _turn(db: AsyncSession, interview_id: uuid.UUID, turn_no: int) -> InterviewTurn:
    turn = await db.scalar(
        select(InterviewTurn)
        .where(InterviewTurn.interview_session_id == interview_id, InterviewTurn.turn_no == turn_no)
        .execution_options(populate_existing=True)
    )
    assert isinstance(turn, InterviewTurn)
    return turn


async def test_answer_saved(db: AsyncSession) -> None:
    interview, _ = await _setup(db)
    await _ask(db, interview.id)

    assert await _answer(db, interview.id, 1, "저는 백엔드 개발자입니다") is None

    turn = await _turn(db, interview.id, 1)
    assert (turn.status, turn.answer_text) == ("answered", "저는 백엔드 개발자입니다")
    assert turn.answered_at is not None
    assert turn.answer_duration_sec is not None and turn.answer_duration_sec >= 0


async def test_answer_turn_mismatch(db: AsyncSession) -> None:
    interview, _ = await _setup(db, current_turn=2)
    await make_turn(db, interview, 1, answered=True)
    await make_turn(db, interview, 2)
    interview_id = interview.id

    assert await _answer(db, interview_id, 3, "앞선 턴") == TurnRejected.NOT_CURRENT_TURN
    assert await _answer(db, interview_id, 1, "지난 턴") == TurnRejected.NOT_CURRENT_TURN
    assert (await _turn(db, interview_id, 2)).status == "asked"


async def test_answer_duplicate_keeps_first(db: AsyncSession) -> None:
    interview, _ = await _setup(db)
    interview_id = interview.id
    await _ask(db, interview_id)

    assert await _answer(db, interview_id, 1, "첫 답변") is None
    assert await _answer(db, interview_id, 1, "두 번째 답변") == TurnRejected.ALREADY_ANSWERED

    assert (await _turn(db, interview_id, 1)).answer_text == "첫 답변"


async def test_answer_not_in_progress(db: AsyncSession) -> None:
    interview, _ = await _setup(db, status="completed", current_turn=1)
    await make_turn(db, interview, 1)

    assert await _answer(db, interview.id, 1, "종료 후 답변") == TurnRejected.NOT_IN_PROGRESS
