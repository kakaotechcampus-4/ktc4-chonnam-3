"""턴 루프. 질문 생성기는 mock, 전송은 리스트에 모은다.

task-15
"""

import uuid
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import InterviewSession, InterviewTurn
from app.features.interview import queries
from app.features.interview.turn_loop import QuestionDraft, ask_next_question, handle_answer

from .factories import make_interview, make_repo, make_run, make_user


class Recorder:
    """mock compose 와 send. compose 는 항상 tech_lead 를 고른다."""

    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []
        self.seen_turns: list[int] = []

    async def compose(self, turns: list[InterviewTurn]) -> QuestionDraft:
        self.seen_turns.append(len(turns))
        return QuestionDraft(persona="tech_lead", text=f"질문 {len(turns) + 1}")

    async def send(self, message: dict[str, Any]) -> None:
        self.sent.append(message)


async def _ask(db: AsyncSession, interview_id: uuid.UUID, rec: Recorder) -> bool:
    return await ask_next_question(
        db, interview_id=interview_id, compose=rec.compose, send=rec.send
    )


async def _start(db: AsyncSession) -> tuple[uuid.UUID, Recorder]:
    run = await make_run(db, await make_user(db))
    interview = await make_interview(db, run, [await make_repo(db, run)])
    rec = Recorder()
    assert await _ask(db, interview.id, rec)
    return interview.id, rec


async def _answer(db: AsyncSession, interview_id: uuid.UUID, rec: Recorder, turn: int) -> None:
    await handle_answer(
        db,
        interview_id=interview_id,
        turn_no=turn,
        text=f"답변 {turn}",
        compose=rec.compose,
        send=rec.send,
    )


async def test_first_question_forced_hr_manager(db: AsyncSession) -> None:
    _, rec = await _start(db)

    assert rec.sent == [{"type": "question", "persona": "hr_manager", "text": "질문 1", "turn": 1}]


async def test_full_interview_until_end(db: AsyncSession) -> None:
    interview_id, rec = await _start(db)

    for turn in range(1, 10):
        await _answer(db, interview_id, rec, turn)

    types = [m["type"] for m in rec.sent]
    assert types == ["question"] + ["answerReceived", "thinking", "question"] * 8 + [
        "answerReceived",
        "thinking",
        "interviewEnd",
    ]
    assert rec.seen_turns == list(range(9))  # 9번째 답변 뒤에는 질문을 만들지 않는다
    turns = await queries.list_turns(db, interview_id=interview_id)
    assert [t.persona for t in turns] == ["hr_manager"] + ["tech_lead"] * 8
    assert all(t.status == "answered" for t in turns)
    interview = await db.get(InterviewSession, interview_id, populate_existing=True)
    assert interview is not None
    assert interview.status == "completed"


async def test_mismatch_and_duplicate_answer_ignored(db: AsyncSession) -> None:
    interview_id, rec = await _start(db)

    await _answer(db, interview_id, rec, 2)  # 현재 턴이 아님
    assert len(rec.sent) == 1
    await _answer(db, interview_id, rec, 1)
    sent_after_first = len(rec.sent)
    await _answer(db, interview_id, rec, 1)  # 이미 답변된 턴

    assert len(rec.sent) == sent_after_first
    turns = await queries.list_turns(db, interview_id=interview_id)
    assert [(t.turn_no, t.answer_text) for t in turns] == [(1, "답변 1"), (2, None)]


async def test_no_question_when_not_in_progress(db: AsyncSession) -> None:
    run = await make_run(db, await make_user(db))
    interview = await make_interview(db, run, [await make_repo(db, run)], status="completed")
    rec = Recorder()

    sent = await _ask(db, interview.id, rec)

    assert sent is False
    assert rec.sent == []


async def test_last_answer_completes_even_if_send_fails(db: AsyncSession) -> None:
    """9번째 답 저장 뒤 첫 전송이 끊겨도 면접은 completed 로 확정된다 (PR #66 리뷰 ①)."""
    interview_id, rec = await _start(db)
    for turn in range(1, 9):
        await _answer(db, interview_id, rec, turn)

    async def broken_send(_: dict[str, Any]) -> None:
        raise ConnectionError("ws closed")

    with pytest.raises(ConnectionError):
        await handle_answer(
            db,
            interview_id=interview_id,
            turn_no=9,
            text="답변 9",
            compose=rec.compose,
            send=broken_send,
        )

    interview = await db.get(InterviewSession, interview_id, populate_existing=True)
    assert interview is not None
    assert interview.status == "completed"
