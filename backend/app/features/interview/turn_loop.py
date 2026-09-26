"""턴 루프 — 질문 생성 → 저장 → question 전송, 답변 저장 → 다음 질문 또는 종료.
WS 전송 계층과 분리한다. 질문 생성기(compose)와 메시지 전송(send)은 인자로 받는다.
★ compose 는 DB session 없이 지난 턴만 받는다 (task-14 Director 계약). 실제 Director 가
  들어오기 전까지 테스트는 mock compose 를 쓴다.
★ 1턴은 persona 를 hr_manager 로 강제한다. 2턴부터의 persona 배분 제어는 Director 몫이다.
★ answerReceived 는 답변 저장 직후 보낸다 — 질문 생성을 기다리지 않는다.
★ turn mismatch·중복 제출은 저장하지 않고 아무것도 보내지 않는다. 계약에 해당 error
  reason 이 없어 임의로 만들지 않는다 (팀 합의 대기).

pipeline.md 4.2 / task-15
"""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import InterviewTurn
from app.features.interview import queries
from app.features.interview.turn_service import complete_interview, save_answer, save_question
from app.shared.enums import Persona


@dataclass(frozen=True)
class QuestionDraft:
    """질문 생성기 출력. save_question 인자와 1:1."""

    persona: str
    text: str
    evidence_ids: tuple[uuid.UUID, ...] = ()
    depth: int = 1
    parent_turn_no: int | None = None
    model: str | None = None
    prompt_version: str | None = None


ComposeQuestion = Callable[[list[InterviewTurn]], Awaitable[QuestionDraft]]
Send = Callable[[dict[str, Any]], Awaitable[None]]


async def ask_next_question(
    db: AsyncSession, *, interview_id: uuid.UUID, compose: ComposeQuestion, send: Send
) -> bool:
    """다음 질문을 만들어 저장하고 question 을 보낸다.

    입력: 면접 id, 질문 생성기, 메시지 전송 함수.
    출력: 보냈으면 True. save_question 이 막으면(진행 중 아님·미답변·턴 소진) False.
    """
    turns = await queries.list_turns(db, interview_id=interview_id)
    draft = await compose(turns)
    turn = await save_question(
        db,
        interview_id=interview_id,
        persona=draft.persona if turns else Persona.HR_MANAGER,
        question_text=draft.text,
        evidence_ids=draft.evidence_ids,
        depth=draft.depth,
        parent_turn_no=draft.parent_turn_no,
        model=draft.model,
        prompt_version=draft.prompt_version,
    )
    if turn is None:
        return False
    await send(
        {
            "type": "question",
            "persona": turn.persona,
            "text": turn.question_text,
            "turn": turn.turn_no,
        }
    )
    return True


async def handle_answer(
    db: AsyncSession,
    *,
    interview_id: uuid.UUID,
    turn_no: int,
    text: str,
    compose: ComposeQuestion,
    send: Send,
) -> None:
    """클라이언트 답변 1건을 처리한다.

    입력: 면접 id, 클라이언트가 보낸 turn·답변 원문, 질문 생성기, 메시지 전송 함수.
    출력: 없음. answerReceived → thinking → (interviewEnd | question) 순서로 보낸다.
    """
    if not await save_answer(db, interview_id=interview_id, turn_no=turn_no, answer_text=text):
        return
    await send({"type": "answerReceived"})
    await send({"type": "thinking"})
    if await complete_interview(db, interview_id=interview_id):
        await send({"type": "interviewEnd"})
        return
    await ask_next_question(db, interview_id=interview_id, compose=compose, send=send)
