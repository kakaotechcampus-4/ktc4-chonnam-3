"""한 턴의 DB 쓰기 — T1 질문 / T2 답변 / T3 분석 / T4 판단.
T1: interview_sessions.current_turn +1 → interview_turns INSERT(status='asked', depth,
    parent_turn_no) → turn_evidences INSERT(usage='question_basis'). 한 트랜잭션.
T2: answer_text UPDATE, status='answered' (제출 1회). 현재 턴의 asked 행만 바꾼다 —
    turn mismatch·이미 답변된 turn 은 저장하지 않는다.
T3: analysis UPDATE
T4: decision UPDATE + interview_sessions.context_state / turn_count / elapsed_sec 갱신
★ depth 1=주제 시작, 2+=꼬리질문. 새 주제로 넘어가면 1로 리셋.
★ 실제 질문 근거가 있으면 질문과 함께 question_basis를 저장한다.
  tech_lead는 가능한 한 근거를 연결하고 domain_lead·hr_manager는 근거 없이도 허용한다.
  첫 HR 질문은 evidence가 없어도 되며 Sprint 1 문서 Claim 생성·연결은 요구하지 않는다.
  답변에서 검증 가능한 주장이 나오면 후속 근거를 evaluation_basis로 연결한다.
★ 질문 값(persona·문장·근거 id)은 Director 출력을 인자로 받는다. T1·T2 는 구현됨,
  T3·T4 와 WS 연결은 구현 대기다.

확정본 §5 / task-15
"""

import uuid
from collections.abc import Collection
from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import Integer, cast, exists, func, insert, literal, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Evidence, InterviewSession, InterviewTurn, TurnEvidence
from app.db.models.interview import PERSONAS


class TurnRejected(StrEnum):
    """질문·답변 저장을 막은 사유. BE 내부 값이다 — WS 로 보낼 reason 은 계약 합의 대기
    (migration.md 같은 턴 중복 답변 PENDING_BE). 호출자가 복구 경로를 고르는 데 쓴다.
    """

    NOT_IN_PROGRESS = "not_in_progress"
    PREVIOUS_UNANSWERED = "previous_unanswered"
    TURNS_EXHAUSTED = "turns_exhausted"
    NOT_CURRENT_TURN = "not_current_turn"
    ALREADY_ANSWERED = "already_answered"


async def save_question(
    db: AsyncSession,
    *,
    interview_id: uuid.UUID,
    persona: str,
    question_text: str,
    evidence_ids: Collection[uuid.UUID] = (),
    depth: int = 1,
    parent_turn_no: int | None = None,
    model: str | None = None,
    prompt_version: str | None = None,
) -> InterviewTurn | TurnRejected:
    """T1 — 다음 턴 질문을 저장하고 commit 한다.

    입력: 면접 id, Director 가 정한 질문 값, 같은 면접의 evidence id 목록(없어도 됨).
    출력: 저장된 턴. 막히면 사유 — NOT_IN_PROGRESS / PREVIOUS_UNANSWERED / TURNS_EXHAUSTED.
    다른 면접의 evidence id 가 섞이거나 persona 가 허용 밖이면 ValueError (저장하지 않는다).
    """
    # 턴 번호를 올린 뒤 DB CHECK 에서 터지면 원인이 흐려지므로 먼저 막는다.
    if persona not in PERSONAS:
        raise ValueError(f"허용되지 않은 persona: {persona}")
    prev_answered = exists().where(
        InterviewTurn.interview_session_id == InterviewSession.id,
        InterviewTurn.turn_no == InterviewSession.current_turn,
        InterviewTurn.status == "answered",
    )
    # 조건 확인과 턴 번호 증가를 UPDATE 한 번으로 — 동시 호출은 세션 행 락에서 한쪽만 통과한다.
    turn_no = await db.scalar(
        update(InterviewSession)
        .where(
            InterviewSession.id == interview_id,
            InterviewSession.status == "in_progress",
            InterviewSession.current_turn < InterviewSession.total_turns,
            or_(InterviewSession.current_turn == 0, prev_answered),
        )
        .values(current_turn=InterviewSession.current_turn + 1)
        .returning(InterviewSession.current_turn)
        .execution_options(synchronize_session=False)
    )
    # 거부 경로는 쓴 게 없어 rollback 하지 않는다 — rollback 은 세션 객체를 만료시키고
    # 호출자의 미커밋 작업까지 지운다. 트랜잭션 종료는 세션을 연 쪽이 맡는다.
    if turn_no is None:
        return await _question_rejection(db, interview_id)

    turn = InterviewTurn(
        interview_session_id=interview_id,
        turn_no=turn_no,
        persona=persona,
        status="asked",
        question_text=question_text,
        depth=depth,
        parent_turn_no=parent_turn_no,
        model=model,
        prompt_version=prompt_version,
        asked_at=datetime.now(UTC),
    )
    db.add(turn)
    await db.flush()

    wanted = set(evidence_ids)
    if wanted:
        linked = await db.execute(
            insert(TurnEvidence).from_select(
                ["turn_id", "evidence_id", "usage"],
                select(literal(turn.id), Evidence.id, literal("question_basis")).where(
                    Evidence.id.in_(wanted), Evidence.interview_session_id == interview_id
                ),
            )
        )
        # 유실·범위 밖 근거를 빈 근거로 숨기지 않는다 (spec/ai/decisions/0012).
        if linked.rowcount != len(wanted):  # type: ignore[attr-defined]
            await db.rollback()
            raise ValueError("evidence_ids 에 이 면접의 근거가 아닌 id 가 있다")

    await db.commit()
    return turn


async def save_answer(
    db: AsyncSession, *, interview_id: uuid.UUID, turn_no: int, answer_text: str
) -> TurnRejected | None:
    """T2 — 현재 턴 답변을 저장하고 commit 한다.

    입력: 면접 id, 클라이언트가 보낸 turn, 답변 원문.
    출력: 저장했으면 None. 막히면 사유 — NOT_IN_PROGRESS / NOT_CURRENT_TURN / ALREADY_ANSWERED.
    ALREADY_ANSWERED 는 재전송이다 — 호출자가 다음 질문·종료 복구를 시도할 수 있다.
    """
    now = datetime.now(UTC)
    is_current = exists().where(
        InterviewSession.id == interview_id,
        InterviewSession.status == "in_progress",
        InterviewSession.current_turn == turn_no,
    )
    # 조건 확인과 저장을 UPDATE 한 번으로 — 동시 중복 제출은 턴 행 락에서 한쪽만 통과한다.
    saved = await db.scalar(
        update(InterviewTurn)
        .where(
            InterviewTurn.interview_session_id == interview_id,
            InterviewTurn.turn_no == turn_no,
            InterviewTurn.status == "asked",
            is_current,
        )
        .values(
            answer_text=answer_text,
            status="answered",
            answered_at=now,
            answer_duration_sec=cast(func.extract("epoch", now - InterviewTurn.asked_at), Integer),
        )
        .returning(InterviewTurn.id)
        .execution_options(synchronize_session=False)
    )
    if saved is None:  # 쓴 게 없어 rollback 하지 않는다 (save_question 참고)
        return await _answer_rejection(db, interview_id, turn_no)
    await db.commit()
    return None


async def complete_interview(db: AsyncSession, *, interview_id: uuid.UUID) -> bool:
    """마지막 턴 답변 후 면접을 completed 로 바꾸고 commit 한다.

    입력: 면접 id.
    출력: 바꿨으면 True. 진행 중이 아니거나 total_turns 미도달이거나 마지막 턴이 미답변이면 False.
    """
    last_answered = exists().where(
        InterviewTurn.interview_session_id == InterviewSession.id,
        InterviewTurn.turn_no == InterviewSession.current_turn,
        InterviewTurn.status == "answered",
    )
    done = await db.scalar(
        update(InterviewSession)
        .where(
            InterviewSession.id == interview_id,
            InterviewSession.status == "in_progress",
            InterviewSession.current_turn == InterviewSession.total_turns,
            last_answered,
        )
        .values(status="completed", completed_at=datetime.now(UTC))
        .returning(InterviewSession.id)
        .execution_options(synchronize_session=False)
    )
    if done is None:  # 쓴 게 없어 rollback 하지 않는다 (save_question 참고)
        return False
    await db.commit()
    return True


# 막힌 경우에만 다시 읽어 사유를 고른다. 판정 자체는 위 조건부 UPDATE 가 했으므로
# 그 사이 상태가 바뀌었다면 사유는 최선 추정이다.
async def _session_state(db: AsyncSession, interview_id: uuid.UUID) -> tuple[str, int, int] | None:
    row = (
        await db.execute(
            select(
                InterviewSession.status,
                InterviewSession.current_turn,
                InterviewSession.total_turns,
            ).where(InterviewSession.id == interview_id)
        )
    ).first()
    return None if row is None else (row[0], row[1], row[2])


async def _question_rejection(db: AsyncSession, interview_id: uuid.UUID) -> TurnRejected:
    state = await _session_state(db, interview_id)
    if state is None or state[0] != "in_progress":
        return TurnRejected.NOT_IN_PROGRESS
    if state[1] >= state[2]:
        return TurnRejected.TURNS_EXHAUSTED
    return TurnRejected.PREVIOUS_UNANSWERED


async def _answer_rejection(
    db: AsyncSession, interview_id: uuid.UUID, turn_no: int
) -> TurnRejected:
    state = await _session_state(db, interview_id)
    if state is None or state[0] != "in_progress":
        return TurnRejected.NOT_IN_PROGRESS
    if state[1] != turn_no:
        return TurnRejected.NOT_CURRENT_TURN
    return TurnRejected.ALREADY_ANSWERED
