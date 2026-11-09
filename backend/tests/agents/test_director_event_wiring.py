"""turn_asked / turn_answered / interview_completed 이벤트 연결: 실제 Director 저장 경로. task-17"""

import json
from collections import Counter
from dataclasses import asdict
from uuid import uuid4

import httpx
from sqlalchemy import select

from app.db.models import Event
from app.features.interview.director_service import process_answer, start_director
from tests.agents.director_helpers import analysis, approved_review, plan, response, seed_turns
from tests.agents.director_helpers import settings as llm_settings
from tests.event_helpers import broken_events as broken_events


async def _counts(sessions) -> Counter[str]:
    async with sessions() as db:
        return Counter(await db.scalars(select(Event.event_name)))


def _handler(failing_analysis: bool = False):
    def handle(request):
        payload = json.loads(json.loads(request.content)["input"][0]["content"][0]["text"])
        if "answer" in payload:
            return response({"invalid": True} if failing_analysis else asdict(analysis()))
        if payload["operation"] == "review":
            return response(approved_review())
        return response(plan(payload["context"]["allowed_personas"][0]))

    return httpx.MockTransport(handle)


async def _answer(sessions, seed, http, turn_no, call_id=None):
    return await process_answer(
        sessions,
        user_id=seed["owner"],
        interview_id=seed["interview_id"],
        turn_no=turn_no,
        text="팀원 담당입니다",
        call_id=call_id or uuid4(),
        settings=llm_settings(),
        http_client=http,
    )


async def _start(sessions, seed, http):
    return await start_director(
        sessions,
        user_id=seed["owner"],
        interview_id=seed["interview_id"],
        call_id=uuid4(),
        settings=llm_settings(),
        http_client=http,
    )


async def test_nine_turn_flow_records_each_event_once_and_replay_adds_none(
    agent_sessions, agent_seed
):
    await seed_turns(agent_sessions, agent_seed, 0)
    async with httpx.AsyncClient(transport=_handler()) as http:
        await _start(agent_sessions, agent_seed, http)
        assert (await _counts(agent_sessions)) == Counter(turn_asked=1)
        replay_call = uuid4()
        for turn_no in range(1, 10):
            call_id = replay_call if turn_no == 9 else None
            await _answer(agent_sessions, agent_seed, http, turn_no, call_id)
        await _answer(agent_sessions, agent_seed, http, 9, replay_call)  # 재전송

    assert await _counts(agent_sessions) == Counter(
        turn_asked=9, turn_answered=9, interview_completed=1
    )
    async with agent_sessions() as db:
        asked = list(
            await db.scalars(
                select(Event.payload).where(Event.event_name == "turn_asked").order_by(Event.id)
            )
        )
    assert sorted(item["turnNo"] for item in asked) == list(range(1, 10))
    assert all(item["persona"] for item in asked)


async def test_analysis_failure_keeps_answered_event_without_completion(agent_sessions, agent_seed):
    await seed_turns(agent_sessions, agent_seed, 9)
    async with httpx.AsyncClient(transport=_handler(failing_analysis=True)) as http:
        result = await _answer(agent_sessions, agent_seed, http, 9)

    assert result.failure is not None and not result.completed
    assert await _counts(agent_sessions) == Counter(turn_answered=1)


async def test_event_failure_does_not_block_director_flow(
    agent_sessions, agent_seed, broken_events
):
    await seed_turns(agent_sessions, agent_seed, 0)
    async with httpx.AsyncClient(transport=_handler()) as http:
        first = await _start(agent_sessions, agent_seed, http)
        assert first.turn_id is not None
        for turn_no in range(1, 10):
            result = await _answer(agent_sessions, agent_seed, http, turn_no)
            assert result.failure is None and result.completed is (turn_no == 9)

    assert await _counts(agent_sessions) == Counter()
