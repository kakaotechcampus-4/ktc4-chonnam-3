"""현재 질문은 과거 답변과 분리하며 마지막 턴도 동일한 계약으로 복원한다."""

from dataclasses import asdict

import pytest
from devon_ai import contracts as c

from app.db.models import InterviewSession, InterviewTurn
from app.features.interview import answer_context
from app.features.interview.agent_context import AgentStateError, load_context


@pytest.mark.parametrize("turn_no", [1, 9])
@pytest.mark.parametrize("answered", [False, True])
async def test_current_question_stays_out_of_history(agent_sessions, agent_seed, turn_no, answered):
    contract = c.QuestionContract(
        "역할 설명", (c.RequiredPoint("role", "담당 역할"),), (), (), "역할"
    )
    personas = ["hr_manager"] + ["tech_lead"] * 6 + ["domain_lead"] * 2
    async with agent_sessions.begin() as db:
        interview = await db.get(InterviewSession, agent_seed["interview_id"])
        interview.current_turn = turn_no
        for number in range(1, turn_no + 1):
            saved = number < turn_no or answered
            db.add(
                InterviewTurn(
                    interview_session_id=interview.id,
                    turn_no=number,
                    persona=personas[number - 1],
                    question_text="담당 역할을 설명해 주세요.",
                    topic_code="role",
                    question_contract=asdict(contract),
                    status="answered" if saved else "asked",
                    answer_text="역할을 설명합니다." if saved else None,
                )
            )
    async with agent_sessions() as db:
        loaded = await answer_context.load_answer_context(
            db,
            user_id=agent_seed["owner"],
            interview_id=agent_seed["interview_id"],
            turn_no=turn_no,
            limits=c.ContextLimits(2, 0, "fixture"),
        )
    assert loaded.context.turn_no == turn_no
    assert len(loaded.context.history) == turn_no - 1
    assert loaded.turn_id == loaded.context.current_turn_id
    assert loaded.answer_text == ("역할을 설명합니다." if answered else None)
    assert loaded.question.data.persona == personas[turn_no - 1]
    assert sum(item.count for item in loaded.context.persona_counts) == turn_no - 1
    if turn_no == 9:
        async with agent_sessions() as db:
            with pytest.raises(AgentStateError):
                await load_context(
                    db,
                    user_id=agent_seed["owner"],
                    interview_id=agent_seed["interview_id"],
                    limits=c.ContextLimits(2, 0, "fixture"),
                )


@pytest.mark.parametrize("turn_no", [0, 10, True])
async def test_invalid_answer_turn_is_controlled(agent_sessions, agent_seed, turn_no):
    async with agent_sessions() as db:
        with pytest.raises(AgentStateError, match="answer_turn_invalid"):
            await answer_context.load_answer_context(
                db,
                user_id=agent_seed["owner"],
                interview_id=agent_seed["interview_id"],
                turn_no=turn_no,
                limits=c.ContextLimits(2, 0, "fixture"),
            )
