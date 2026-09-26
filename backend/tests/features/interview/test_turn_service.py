"""턴 저장 service. Director 출력은 인자 고정값으로 대신한다.

task-15
"""

import uuid
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import InterviewSession, InterviewTurn, TurnEvidence
from app.features.interview.turn_service import save_question

from .factories import make_evidence, make_interview, make_repo, make_run, make_turn, make_user


async def _setup(db: AsyncSession, **overrides: Any) -> tuple[InterviewSession, Any]:
    run = await make_run(db, await make_user(db))
    repo = await make_repo(db, run)
    return await make_interview(db, run, [repo], **overrides), repo


async def _ask(db: AsyncSession, interview_id: uuid.UUID, **kw: Any) -> InterviewTurn | None:
    return await save_question(
        db, interview_id=interview_id, persona="hr_manager", question_text="자기소개", **kw
    )


async def test_first_question_without_evidence(db: AsyncSession) -> None:
    interview, _ = await _setup(db)

    turn = await _ask(db, interview.id)

    assert turn is not None
    assert (turn.turn_no, turn.status, turn.persona) == (1, "asked", "hr_manager")
    await db.refresh(interview)
    assert interview.current_turn == 1
    assert await db.scalar(select(TurnEvidence).where(TurnEvidence.turn_id == turn.id)) is None


async def test_question_links_evidence(db: AsyncSession) -> None:
    interview, repo = await _setup(db)
    evidences = [await make_evidence(db, interview, repo) for _ in range(2)]

    turn = await _ask(db, interview.id, evidence_ids=[e.id for e in evidences])

    assert turn is not None
    rows = (await db.scalars(select(TurnEvidence).where(TurnEvidence.turn_id == turn.id))).all()
    assert {r.evidence_id for r in rows} == {e.id for e in evidences}
    assert {r.usage for r in rows} == {"question_basis"}


async def test_next_question_after_answer(db: AsyncSession) -> None:
    interview, _ = await _setup(db, current_turn=1)
    await make_turn(db, interview, 1, answered=True)

    turn = await _ask(db, interview.id, depth=2, parent_turn_no=1)

    assert turn is not None
    assert (turn.turn_no, turn.depth, turn.parent_turn_no) == (2, 2, 1)


@pytest.mark.parametrize(
    ("overrides", "last_answered"),
    [
        ({"current_turn": 1}, False),  # 이전 턴 미답변
        ({"current_turn": 9}, True),  # total_turns 도달
        ({"status": "completed"}, None),  # 진행 중 아님
    ],
)
async def test_question_blocked(
    db: AsyncSession, overrides: dict[str, Any], last_answered: bool | None
) -> None:
    interview, _ = await _setup(db, **overrides)
    if last_answered is not None:
        await make_turn(db, interview, overrides["current_turn"], answered=last_answered)

    assert await _ask(db, interview.id) is None


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
