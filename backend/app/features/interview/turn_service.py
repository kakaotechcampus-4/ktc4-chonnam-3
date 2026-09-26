"""한 턴의 DB 쓰기 — T1 질문 / T2 답변 / T3 분석 / T4 판단.
T1: interview_sessions.current_turn +1 → interview_turns INSERT(status='asked', depth,
    parent_turn_no) → turn_evidences INSERT(usage='question_basis'). 한 트랜잭션.
T2: answer_text UPDATE, status='answered' (제출 1회)
T3: analysis UPDATE
T4: decision UPDATE + interview_sessions.context_state / turn_count / elapsed_sec 갱신
★ depth 1=주제 시작, 2+=꼬리질문. 새 주제로 넘어가면 1로 리셋.
★ 실제 질문 근거가 있으면 질문과 함께 question_basis를 저장한다.
  tech_lead는 가능한 한 근거를 연결하고 domain_lead·hr_manager는 근거 없이도 허용한다.
  첫 HR 질문은 evidence가 없어도 되며 Sprint 1 문서 Claim 생성·연결은 요구하지 않는다.
  답변에서 검증 가능한 주장이 나오면 후속 근거를 evaluation_basis로 연결한다.
★ 질문 값(persona·문장·근거 id)은 Director 출력을 인자로 받는다. T1 은 구현됨,
  T2~T4 와 WS 연결은 구현 대기다.

확정본 §5 / task-15
"""

import uuid
from collections.abc import Collection
from datetime import UTC, datetime

from sqlalchemy import exists, insert, literal, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Evidence, InterviewSession, InterviewTurn, TurnEvidence


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
) -> InterviewTurn | None:
    """T1 — 다음 턴 질문을 저장하고 commit 한다.

    입력: 면접 id, Director 가 정한 질문 값, 같은 면접의 evidence id 목록(없어도 됨).
    출력: 저장된 턴. 진행 중이 아니거나 이전 턴이 미답변이거나 total_turns 에 도달했으면 None.
    다른 면접의 evidence id 가 섞이면 ValueError (아무것도 저장하지 않는다).
    """
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
    if turn_no is None:
        await db.rollback()
        return None

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
