"""확정 부모 관계를 REST·WS·리포트가 같은 메인 번호로 표시한다."""

import json
from dataclasses import asdict
from uuid import uuid4

import httpx
from sqlalchemy import select

from app.db.models import InterviewSession, InterviewTurn
from app.features.interview.director_service import process_answer
from tests.agents.director_helpers import (
    analysis,
    approved_review,
    plan,
    response,
    seed_turns,
    settings,
)
from tests.agents.test_director_ws import connect_ws as connect_ws
from tests.features.report.factories import make_report, seed_criteria


async def test_nonadjacent_parent_uses_root_main_index_in_rest_ws_and_report(
    agent_sessions, agent_seed, connect_ws
):
    await seed_turns(agent_sessions, agent_seed, 3)
    async with agent_sessions() as db:
        parent = await db.scalar(select(InterviewTurn).where(InterviewTurn.turn_no == 2))
        parent_id = str(parent.id)
    requests = []

    async def model(request):
        payload = json.loads(json.loads(request.content)["input"][0]["content"][0]["text"])
        requests.append(payload)
        if "answer" in payload:
            return response(asdict(analysis()))
        if payload["operation"] == "review":
            return response(approved_review())
        candidate = plan(payload["context"]["allowed_personas"][0])
        if payload["context"]["turn_no"] == 4:
            candidate["question"]["question_type"] = "follow_up"
            candidate["question"]["parent_turn_id"] = parent_id
        return response(candidate)

    async with httpx.AsyncClient(transport=httpx.MockTransport(model)) as http:
        execution = await process_answer(
            agent_sessions,
            user_id=agent_seed["owner"],
            interview_id=agent_seed["interview_id"],
            turn_no=3,
            text="팀원 담당입니다",
            call_id=uuid4(),
            settings=settings(),
            http_client=http,
        )
        assert execution.failure is None and execution.next_turn_id is not None
        async with agent_sessions() as db:
            child = await db.get(InterviewTurn, execution.next_turn_id)
            assert (child.turn_no, child.depth, child.parent_turn_no) == (4, 2, 2)
        with connect_ws() as (client, app, path, _, _):
            detail = client.get(f"/api/interviews/{agent_seed['interview_id']}")
            assert detail.status_code == 200, detail.text
            turns = detail.json()["turns"]
            rest_parent, rest_child = turns[1], turns[3]
            with client.websocket_connect(path, headers={"origin": "http://localhost:5173"}) as ws:
                question = ws.receive_json()
            assert question["type"] == "question" and question["turn"] == 4
            for number in range(4, 10):
                continued = await process_answer(
                    agent_sessions,
                    user_id=agent_seed["owner"],
                    interview_id=agent_seed["interview_id"],
                    turn_no=number,
                    text="팀원 담당입니다",
                    call_id=uuid4(),
                    settings=settings(),
                    http_client=http,
                )
                assert continued.failure is None and continued.discard_reason is None
                assert continued.completed is (number == 9)
            async with agent_sessions.begin() as db:
                interview = await db.get(InterviewSession, agent_seed["interview_id"])
                assert interview.status == "completed"
                await seed_criteria(db)
                await make_report(db, interview)
            report = client.get(f"/api/interviews/{agent_seed['interview_id']}/report")
            assert report.status_code == 200, report.text
            report_turns = report.json()["turns"]
    assert len(requests) == 19
    assert rest_parent["mainIndex"] == report_turns[1]["mainIndex"] == 2
    assert (
        rest_child["followUpDepth"]
        == question["followUpDepth"]
        == report_turns[3]["followUpDepth"]
        == 1
    )
    assert rest_child["mainIndex"] == question["mainIndex"] == report_turns[3]["mainIndex"] == 2
