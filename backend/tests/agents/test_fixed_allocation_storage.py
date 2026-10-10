"""실제 DB 이력과 프레임으로 기술 6·도메인 2·HR 1의 생성·저장 경계를 검증한다."""

import json
from collections import Counter
from dataclasses import asdict
from uuid import uuid4

import httpx
import pytest
from devon_ai import contracts as c
from sqlalchemy import delete, func, select, update

from app.db.models import (
    DomainQuestionFrame,
    InterviewSession,
    InterviewTurn,
    JobPosting,
    LLMCallRecord,
)
from app.features.interview.agent_context import AgentStateError, load_context
from tests.agents.test_agent_storage import invoke, output, prepared_contract, response


async def context_for(sessions, seed):
    async with sessions() as db:
        return await load_context(
            db,
            user_id=seed["owner"],
            interview_id=seed["interview_id"],
            limits=c.ContextLimits(2, 0, "fixture"),
        )


async def answered_history(sessions, seed, personas):
    async with sessions.begin() as db:
        db.add_all(
            InterviewTurn(
                interview_session_id=seed["interview_id"],
                turn_no=number,
                persona=persona,
                question_text="이전 질문",
                question_contract=asdict(prepared_contract()),
                answer_text="이전 답변",
                status="answered",
            )
            for number, persona in enumerate(personas, 1)
        )
        await db.execute(update(InterviewSession).values(current_turn=len(personas)))


def candidate(persona):
    value = json.loads(output())
    value["persona"] = persona
    return json.dumps(value)


def forbidden_provider(request):
    pytest.fail("invalid state reached provider")


async def test_unknown_category_uses_etc_context_without_rewriting_posting(
    agent_sessions, agent_seed
):
    context = await context_for(agent_sessions, agent_seed)
    assert [(frame.id, frame.category) for frame in context.domain_frames] == [
        (str(agent_seed["frame_id"]), "etc")
    ]
    assert context.allowed_personas == ("hr_manager",)
    async with agent_sessions() as db:
        assert (await db.get(JobPosting, agent_seed["posting_id"])).domain_category is None


async def test_known_category_keeps_its_active_frames(agent_sessions, agent_seed):
    frame_id = uuid4()
    async with agent_sessions.begin() as db:
        await db.execute(update(JobPosting).values(domain_category="finance"))
        db.add(
            DomainQuestionFrame(
                id=frame_id,
                domain_category="finance",
                axis="privacy_sensitive_data",
                frame_text="금융 정보의 접근 권한은 어떻게 관리하나요?",
                is_active=True,
            )
        )
    context = await context_for(agent_sessions, agent_seed)
    assert [(frame.id, frame.category) for frame in context.domain_frames] == [
        (str(frame_id), "finance")
    ]
    async with agent_sessions() as db:
        assert (await db.get(JobPosting, agent_seed["posting_id"])).domain_category == "finance"


@pytest.mark.parametrize("missing", ["etc", "inactive_etc", "known", "inactive_known"])
async def test_required_frames_block_before_first_hr_without_side_effects(
    agent_sessions, agent_seed, missing
):
    async with agent_sessions.begin() as db:
        if missing == "etc":
            await db.execute(delete(DomainQuestionFrame))
        elif missing == "inactive_etc":
            await db.execute(update(DomainQuestionFrame).values(is_active=False))
        else:
            await db.execute(update(JobPosting).values(domain_category="finance"))
            if missing == "inactive_known":
                db.add(
                    DomainQuestionFrame(
                        domain_category="finance",
                        axis="privacy_sensitive_data",
                        frame_text="비활성 프레임",
                        is_active=False,
                    )
                )
    async with httpx.AsyncClient(transport=httpx.MockTransport(forbidden_provider)) as http:
        with pytest.raises(AgentStateError, match="domain_frames_unavailable"):
            await invoke(agent_sessions, agent_seed, http)
    async with agent_sessions() as db:
        assert await db.scalar(select(func.count()).select_from(InterviewTurn)) == 0
        assert await db.scalar(select(func.count()).select_from(LLMCallRecord)) == 0
        assert (await db.get(InterviewSession, agent_seed["interview_id"])).current_turn == 0


async def test_frame_changed_during_provider_discards_success(agent_sessions, agent_seed):
    async def transport(request):
        async with agent_sessions.begin() as db:
            await db.execute(update(DomainQuestionFrame).values(frame_text="변경된 프레임"))
        return response(output())

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as http:
        result = await invoke(agent_sessions, agent_seed, http)
    assert result.turn_id is None and result.discard_reason == "context_changed"
    assert result.failure is None
    async with agent_sessions() as db:
        record = await db.get(LLMCallRecord, result.call_id)
        assert record.discard_reason == "context_changed" and len(record.attempts) == 1
        assert await db.scalar(select(func.count()).select_from(InterviewTurn)) == 0
        assert (await db.get(InterviewSession, agent_seed["interview_id"])).current_turn == 0


async def test_used_domain_quota_allows_tech_without_frames(agent_sessions, agent_seed):
    await answered_history(agent_sessions, agent_seed, ["hr_manager", "domain_lead", "domain_lead"])
    async with agent_sessions.begin() as db:
        await db.execute(delete(DomainQuestionFrame))
    context = await context_for(agent_sessions, agent_seed)
    assert context.domain_frames == () and context.allowed_personas == ("tech_lead",)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: response(candidate("tech_lead")))
    ) as http:
        result = await invoke(agent_sessions, agent_seed, http)
    assert result.turn_id is not None and result.failure is None
    async with agent_sessions() as db:
        assert (await db.get(InterviewTurn, result.turn_id)).persona == "tech_lead"
        assert (await db.get(InterviewSession, agent_seed["interview_id"])).current_turn == 4


async def test_nine_questions_use_exact_quotas_and_replay_never_adds_a_tenth(
    agent_sessions, agent_seed
):
    personas = ["hr_manager", "tech_lead", "domain_lead", "tech_lead", "domain_lead"] + [
        "tech_lead"
    ] * 4
    sent = []

    def transport(request):
        persona = personas[len(sent)]
        sent.append(persona)
        return response(candidate(persona))

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as http:
        for number, persona in enumerate(personas, 1):
            call_id = uuid4()
            result = await invoke(agent_sessions, agent_seed, http, call_id=call_id)
            assert result.turn_id is not None and result.failure is None
            replay = await invoke(agent_sessions, agent_seed, http, call_id=call_id)
            assert replay == result
            async with agent_sessions.begin() as db:
                turn = await db.get(InterviewTurn, result.turn_id)
                assert (turn.turn_no, turn.persona, turn.status) == (number, persona, "asked")
                turn.answer_text, turn.status = "제 답변입니다.", "answered"
        with pytest.raises(AgentStateError, match="interview_state_invalid"):
            await invoke(agent_sessions, agent_seed, http)
    assert sent == personas
    async with agent_sessions() as db:
        turns = (await db.scalars(select(InterviewTurn).order_by(InterviewTurn.turn_no))).all()
        assert [turn.persona for turn in turns] == personas
        assert Counter(turn.persona for turn in turns) == {
            "hr_manager": 1,
            "tech_lead": 6,
            "domain_lead": 2,
        }
        assert await db.scalar(select(func.count()).select_from(LLMCallRecord)) == 9
        assert (await db.get(InterviewSession, agent_seed["interview_id"])).current_turn == 9


@pytest.mark.parametrize(
    ("history", "persona"),
    [(["hr_manager"], "hr_manager"), (["hr_manager"] + ["tech_lead"] * 6, "tech_lead")],
)
async def test_forbidden_persona_is_semantic_failure_without_saving_question(
    agent_sessions, agent_seed, history, persona
):
    await answered_history(agent_sessions, agent_seed, history)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: response(candidate(persona)))
    ) as http:
        result = await invoke(agent_sessions, agent_seed, http)
    assert result.turn_id is None and result.failure.stage == "semantic"
    async with agent_sessions() as db:
        record = await db.get(LLMCallRecord, result.call_id)
        assert record.failure["stage"] == "semantic" and len(record.attempts) == 1
        assert await db.scalar(select(func.count()).select_from(InterviewTurn)) == len(history)
        assert (await db.get(InterviewSession, agent_seed["interview_id"])).current_turn == len(
            history
        )


@pytest.mark.parametrize(
    "history", [["hr_manager", "hr_manager"], ["tech_lead"], ["hr_manager"] + ["domain_lead"] * 3]
)
async def test_invalid_existing_history_never_reaches_provider(agent_sessions, agent_seed, history):
    await answered_history(agent_sessions, agent_seed, history)
    async with httpx.AsyncClient(transport=httpx.MockTransport(forbidden_provider)) as http:
        with pytest.raises(AgentStateError):
            await invoke(agent_sessions, agent_seed, http)
    async with agent_sessions() as db:
        assert await db.scalar(select(func.count()).select_from(LLMCallRecord)) == 0
        assert await db.scalar(select(func.count()).select_from(InterviewTurn)) == len(history)
