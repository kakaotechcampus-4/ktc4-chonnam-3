"""자동 Director의 직접 답변 저장도 기존 면접 시작 시각 보정을 지킨다."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.db.models import InterviewSession, InterviewTurn
from app.features.interview.director_service import process_answer
from tests.agents.director_helpers import seed_turns, settings


class StopAfterSaved(Exception):
    pass


@pytest.mark.parametrize("clock", ["missing", "started", "missing_asked_at"])
async def test_answer_sets_clock_before_model_io_and_preserves_started_clock(
    agent_sessions, agent_seed, clock
):
    await seed_turns(agent_sessions, agent_seed)
    now = datetime.now(UTC)
    started = now - timedelta(seconds=90) if clock == "started" else None
    asked = None if clock == "missing_asked_at" else now - timedelta(seconds=30)
    async with agent_sessions.begin() as db:
        interview = await db.get(InterviewSession, agent_seed["interview_id"])
        interview.started_at = started
        turn = await db.scalar(select(InterviewTurn).where(InterviewTurn.turn_no == 1))
        turn.asked_at = asked

    async def answer_saved():
        async with agent_sessions() as db:
            interview = await db.get(InterviewSession, agent_seed["interview_id"])
            turn = await db.scalar(select(InterviewTurn).where(InterviewTurn.turn_no == 1))
            assert turn.status == "answered" and turn.answer_text == "팀원 담당입니다"
            assert interview.started_at is not None
            if started is not None:
                assert interview.started_at == started
            elif asked is not None:
                assert interview.started_at == asked
            else:
                assert now <= interview.started_at <= turn.answered_at
        # 저장 경계를 검증한 뒤 모델 호출 전에 중단한다.
        raise StopAfterSaved

    with pytest.raises(StopAfterSaved):
        await process_answer(
            agent_sessions,
            user_id=agent_seed["owner"],
            interview_id=agent_seed["interview_id"],
            turn_no=1,
            text="팀원 담당입니다",
            call_id=uuid4(),
            settings=settings(),
            on_answer_saved=answer_saved,
        )
