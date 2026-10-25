"""실제 ASGI WebSocket·PostgreSQL·Redis와 HTTP 모델 대역으로 공개 흐름을 검사한다."""

import asyncio
import base64
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from contextlib import ExitStack, contextmanager
from dataclasses import asdict, replace

import httpx
import pytest
from devon_ai import contracts as c
from fastapi.testclient import TestClient
from sqlalchemy import select
from starlette.testclient import WebSocketDenialResponse
from starlette.websockets import WebSocket, WebSocketDisconnect

from app.core.config import Settings
from app.db.models import Evidence, InterviewSession, InterviewTurn, LLMCallRecord
from tests.agents.test_director_runtime_service import analysis, contract, response, seed_turns


@pytest.fixture
def connect_ws(agent_sessions, agent_seed, test_redis_url):
    @contextmanager
    def connect(handler=None, *, user_id=None):
        from app.features.interview import ws
        from app.features.interview.service import _issue_session_id
        from app.main import create_app

        config = Settings(
            _env_file=None,
            database_url=str(agent_sessions.kw["bind"].url),
            redis_url=test_redis_url,
            token_encryption_key=base64.b64encode(bytes(range(32))).decode(),
            github_client_id="fixture",
            github_client_secret="fixture",
            openai_api_key="fixture-key",
            llm_timeout_seconds=2,
            llm_max_output_tokens=2048,
            llm_max_input_bytes=262144,
            llm_max_response_bytes=262144,
        )
        app = create_app(config)
        if not any(
            getattr(route, "path", "") == "/api/ws/interviews/{session_id}" for route in app.routes
        ):
            app.include_router(ws.router, prefix="/api")
        with TestClient(app) as client:
            app.state.session_factory = agent_sessions
            http = httpx.AsyncClient(transport=httpx.MockTransport(handler or unexpected_model))
            app.state.http_client = http

            async def setup():
                sid = await app.state.sessions.create(user_id or agent_seed["owner"])
                realtime = await _issue_session_id(
                    app.state.redis,
                    interview_id=agent_seed["interview_id"],
                    user_id=agent_seed["owner"],
                )
                return sid, realtime

            sid, realtime = client.portal.call(setup)
            client.cookies.set("devon_session", sid)
            try:
                yield client, app, f"/api/ws/interviews/{realtime}", sid, realtime
            finally:
                client.portal.call(http.aclose)

    return connect


def unexpected_model(request):
    pytest.fail("저장된 질문 재전달에서 모델을 호출했다")


async def test_reconnect_replays_stored_question_and_rebuilds_snapshot_without_a_model(
    agent_sessions,
    agent_seed,
    connect_ws,
):
    await seed_turns(agent_sessions, agent_seed)
    with connect_ws() as (client, app, path, _, realtime):
        for _ in range(2):
            with client.websocket_connect(
                path, headers={"origin": "http://localhost:5173"}
            ) as socket:
                assert socket.receive_json() == {
                    "type": "question",
                    "persona": "hr_manager",
                    "text": "본인의 역할을 설명해 주세요.",
                    "turn": 1,
                }

        async def cached():
            return await app.state.redis.get(f"iv:ctx:{agent_seed['interview_id']}")

        snapshot = json.loads(client.portal.call(cached))
        assert snapshot["currentTurn"] == 1
        assert snapshot["turns"][0]["answer"] is None

        async def ttl():
            return [
                await app.state.redis.ttl(key)
                for key in (
                    f"rt:{realtime}",
                    f"rt:interview:{agent_seed['interview_id']}",
                )
            ]

        assert all(value > 7000 for value in client.portal.call(ttl))


@pytest.mark.parametrize("case", ["missing_cookie", "origin", "other_user"])
async def test_ws_denies_unauthed_wrong_origin_or_another_users_realtime_session(
    agent_sessions,
    agent_seed,
    connect_ws,
    case,
):
    await seed_turns(agent_sessions, agent_seed)
    with connect_ws(user_id=agent_seed["other"] if case == "other_user" else None) as (
        client,
        _,
        path,
        _,
        _,
    ):
        if case == "missing_cookie":
            client.cookies.clear()
        origin = "https://attacker.invalid" if case == "origin" else "http://localhost:5173"
        with pytest.raises(WebSocketDenialResponse) as caught:
            with client.websocket_connect(path, headers={"origin": origin}):
                pytest.fail("거부해야 할 연결을 수락했다")
        assert caught.value.status_code == (
            409 if case == "other_user" else 403 if case == "origin" else 401
        )


async def test_normal_nine_turn_ws_persists_each_answer_before_ack_and_ends_after_final_analysis(
    agent_sessions,
    agent_seed,
    connect_ws,
):
    await seed_turns(agent_sessions, agent_seed)
    requests = []

    async def handle(request):
        body = json.loads(request.content)
        payload = json.loads(body["input"][0]["content"][0]["text"])
        requests.append(body["text"]["format"]["name"])
        async with agent_sessions.begin() as db:
            interview = await db.get(
                InterviewSession, agent_seed["interview_id"], with_for_update=True
            )
            assert interview.status == "in_progress"
        if payload.get("operation") == "review":
            return response(
                {
                    "plan_valid": True,
                    "context_valid": True,
                    "wording_valid": True,
                    "contract_matches": True,
                    "safe_alternative": True,
                    "reason_summary": "적합",
                }
            )
        if payload.get("operation") == "plan":
            persona = payload["context"]["allowed_personas"][0]
            return response(
                {
                    "question": {
                        "persona": persona,
                        "text": "본인의 역할을 설명해 주세요.",
                        "topic_code": "role",
                        "question_contract": asdict(contract()),
                        "evidence_refs": [],
                        "jd_requirement_ids": [],
                    },
                    "intent": "역할 확인",
                    "reason_summary": "현재 맥락에서 역할 확인",
                }
            )
        return response(asdict(analysis()))

    with connect_ws(handle) as (client, _, path, _, _):
        with client.websocket_connect(path, headers={"origin": "http://localhost:5173"}) as socket:
            assert socket.receive_json()["turn"] == 1
            for turn in range(1, 10):
                socket.send_json({"type": "answer", "turn": turn, "text": "팀원 담당입니다"})
                assert socket.receive_json() == {"type": "answerReceived"}
                assert socket.receive_json() == {"type": "thinking"}
                event = socket.receive_json()
                if turn == 9:
                    assert event == {"type": "interviewEnd"}
                else:
                    assert event["type"] == "question" and event["turn"] == turn + 1
                    if turn == 1:
                        socket.send_json({"type": "answer", "turn": 1, "text": "덮어쓰기 시도"})
                        assert socket.receive_json()["reason"] == "answer_stale_turn"
    async with agent_sessions() as db:
        interview = await db.get(InterviewSession, agent_seed["interview_id"])
        turns = list(await db.scalars(select(InterviewTurn).order_by(InterviewTurn.turn_no)))
        assert interview.status == "completed"
        assert len(turns) == 9 and all(turn.status == "answered" for turn in turns)
        assert all(turn.answer_text == "팀원 담당입니다" for turn in turns)
        assert all(turn.analysis is not None for turn in turns)
        assert [turn.persona for turn in turns].count("tech_lead") == 6
    assert len(requests) == 25


async def test_stale_and_invalid_answers_never_overwrite_the_current_turn(
    agent_sessions,
    agent_seed,
    connect_ws,
):
    await seed_turns(agent_sessions, agent_seed)
    with connect_ws() as (client, _, path, _, _):
        with client.websocket_connect(path, headers={"origin": "http://localhost:5173"}) as socket:
            socket.receive_json()
            for value, reason in [
                ({"type": "answer", "turn": 2, "text": "오래된 답변"}, "answer_stale_turn"),
                ({"type": "answer", "turn": True, "text": "답변"}, "answer_rejected"),
                ({"type": "answer", "turn": 1, "text": "x" * 2001}, "answer_too_long"),
            ]:
                socket.send_json(value)
                assert socket.receive_json()["reason"] == reason
    async with agent_sessions() as db:
        assert (await db.scalar(select(InterviewTurn))).answer_text is None
        assert await db.scalar(select(LLMCallRecord.id)) is None


@pytest.mark.parametrize("status", ["completed", "abandoned"])
async def test_ended_interview_reconnect_is_denied_before_accept(
    agent_sessions, agent_seed, connect_ws, status
):
    await seed_turns(agent_sessions, agent_seed, 9)
    async with agent_sessions.begin() as db:
        interview = await db.get(InterviewSession, agent_seed["interview_id"])
        interview.status = status
    with connect_ws() as (client, _, path, _, _):
        with pytest.raises(WebSocketDenialResponse) as caught:
            with client.websocket_connect(path, headers={"origin": "http://localhost:5173"}):
                pytest.fail("종료된 면접 연결을 수락했다")
        assert caught.value.status_code == 409
        snapshot = client.get(
            f"/api/interviews/{agent_seed['interview_id']}",
            headers={"origin": "http://localhost:5173"},
        )
        assert snapshot.status_code == 200 and snapshot.json()["status"] == status


async def test_answered_current_turn_does_not_resume_a_failed_or_pending_model_call(
    agent_sessions,
    agent_seed,
    connect_ws,
):
    await seed_turns(agent_sessions, agent_seed)
    async with agent_sessions.begin() as db:
        turn = await db.scalar(select(InterviewTurn))
        turn.status, turn.answer_text = "answered", "팀원 담당입니다"
    with connect_ws() as (client, _, path, _, _):
        with client.websocket_connect(path, headers={"origin": "http://localhost:5173"}) as socket:
            assert socket.receive_json()["reason"] == "question_failed"
            with pytest.raises(WebSocketDisconnect):
                socket.receive_json()
