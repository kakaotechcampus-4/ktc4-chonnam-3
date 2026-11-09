"""명시 중단과 동시에 도착한 모델 결과·소켓이 중단 상태를 되살리지 않는다."""

import asyncio
import json
from dataclasses import asdict
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select
from starlette.websockets import WebSocketDisconnect

from app.db.models import InterviewSession, InterviewTurn, LLMCallRecord
from app.features.interview import service
from tests.agents.director_helpers import (
    analysis,
    approved_review,
    plan,
    response,
    seed_turns,
    settings,
)
from tests.agents.test_director_ws import connect_ws as _connect_ws

connect_ws = _connect_ws


async def test_abandon_closes_open_socket_without_sending_more_questions(
    agent_sessions, agent_seed, connect_ws
):
    await seed_turns(agent_sessions, agent_seed)
    with connect_ws() as (client, _, path, _, _):
        with client.websocket_connect(path, headers={"origin": "http://localhost:5173"}) as socket:
            assert socket.receive_json()["type"] == "question"
            stopped = client.post(
                f"/api/interviews/{agent_seed['interview_id']}/abandon",
                headers={"origin": "http://localhost:5173"},
            )
            assert stopped.status_code == 204
            with pytest.raises(WebSocketDisconnect):
                socket.receive_json()
        restored = client.get(f"/api/interviews/{agent_seed['interview_id']}")
        assert restored.json()["status"] == "abandoned"


@pytest.mark.parametrize("phase,turn_no", [("analysis", 1), ("analysis", 9), ("director", 0)])
async def test_abandon_discards_inflight_model_result(
    agent_sessions, agent_seed, redis, phase, turn_no
):
    from app.features.interview.director_service import process_answer, start_director

    await seed_turns(agent_sessions, agent_seed, turn_no)
    started, release = asyncio.Event(), asyncio.Event()
    call_id = uuid4()

    async def provider(request):
        started.set()
        await release.wait()
        if phase == "analysis":
            return response(asdict(analysis()))
        payload = json.loads(json.loads(request.content)["input"][0]["content"][0]["text"])
        return response(plan() if payload["operation"] == "plan" else approved_review())

    options = dict(
        user_id=agent_seed["owner"],
        interview_id=agent_seed["interview_id"],
        call_id=call_id,
        settings=settings(),
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as http:
        action = (
            process_answer(
                agent_sessions, **options, turn_no=turn_no, text="팀원 담당입니다", http_client=http
            )
            if phase == "analysis"
            else start_director(agent_sessions, **options, http_client=http)
        )
        task = asyncio.create_task(action)
        await asyncio.wait_for(started.wait(), 5)
        async with agent_sessions() as db:
            await service.abandon_interview(
                db,
                redis,
                user_id=agent_seed["owner"],
                interview_id=agent_seed["interview_id"],
            )
        release.set()
        result = await task
    assert result.discard_reason == "context_changed"
    async with agent_sessions() as db:
        interview = await db.get(InterviewSession, agent_seed["interview_id"])
        record = await db.get(LLMCallRecord, call_id)
        turns = list(await db.scalars(select(InterviewTurn).order_by(InterviewTurn.turn_no)))
        assert interview.status == "abandoned" and interview.completed_at is None
        assert record.discard_reason == "context_changed" and record.turn_id is None
        if phase == "analysis":
            assert len(turns) == turn_no
            assert turns[-1].answer_text == "팀원 담당입니다"
            assert turns[-1].analysis is None and turns[-1].decision is None
        else:
            assert turns == []
