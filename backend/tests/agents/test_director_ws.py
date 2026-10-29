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
from tests.agents.director_helpers import analysis, contract, response, seed_turns


@pytest.fixture
def connect_ws(agent_sessions, agent_seed, test_redis_url):
    @contextmanager
    def connect(handler=None, *, user_id=None):
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


@pytest.mark.parametrize("separate_app", [False, True])
async def test_new_connection_closes_previous_socket_and_preserves_its_own_lease(
    agent_sessions,
    agent_seed,
    connect_ws,
    monkeypatch,
    separate_app,
):
    events = []
    accept, close = WebSocket.accept, WebSocket.close

    async def accepting(socket, *args, **kwargs):
        events.append("accept:" + socket.headers["x-test-connection"])
        await accept(socket, *args, **kwargs)

    async def closing(socket, *args, **kwargs):
        await close(socket, *args, **kwargs)
        events.append("close:" + socket.headers["x-test-connection"])

    monkeypatch.setattr(WebSocket, "accept", accepting)
    monkeypatch.setattr(WebSocket, "close", closing)
    await seed_turns(agent_sessions, agent_seed)
    with connect_ws() as (client, app, path, _, realtime), ExitStack() as previous:
        old = previous.enter_context(
            client.websocket_connect(
                path, headers={"origin": "http://localhost:5173", "x-test-connection": "old"}
            )
        )
        question = old.receive_json()

        async def owner():
            return await app.state.redis.get(f"ws:lock:{realtime}")

        old_nonce = client.portal.call(owner)
        with ExitStack() as candidates:
            candidate = candidates.enter_context(connect_ws())[0] if separate_app else client
            with candidate.websocket_connect(
                path, headers={"origin": "http://localhost:5173", "x-test-connection": "new"}
            ) as new:
                assert new.receive_json() == question
                assert events[:3] == ["accept:old", "close:old", "accept:new"]
                with pytest.raises(WebSocketDisconnect):
                    old.receive_json()
                new_nonce = client.portal.call(owner)
                assert new_nonce is not None and new_nonce != old_nonce
                previous.close()
                assert client.portal.call(owner) == new_nonce
                new.send_json({"type": "answer", "turn": 2, "text": "이전 턴 확인"})
                assert new.receive_json()["reason"] == "answer_stale_turn"


@pytest.mark.parametrize("case", ["expired", "deleted"])
async def test_login_session_loss_does_not_disconnect_an_authenticated_interview(
    agent_sessions, agent_seed, connect_ws, case
):
    await seed_turns(agent_sessions, agent_seed, 9)
    with connect_ws(lambda request: response(asdict(analysis()))) as (client, app, path, sid, _):
        with client.websocket_connect(path, headers={"origin": "http://localhost:5173"}) as socket:
            assert socket.receive_json()["turn"] == 9

            async def invalidate():
                if case == "expired":
                    await app.state.redis.expire(f"auth:sess:{sid}", 0)
                else:
                    await app.state.sessions.delete(sid)

            client.portal.call(invalidate)
            socket.send_json({"type": "answer", "turn": 9, "text": "팀원 담당입니다"})
            assert socket.receive_json() == {"type": "answerReceived"}
            assert socket.receive_json() == {"type": "thinking"}
            assert socket.receive_json() == {"type": "interviewEnd"}
        with pytest.raises(WebSocketDenialResponse) as caught:
            with client.websocket_connect(path, headers={"origin": "http://localhost:5173"}):
                pytest.fail("만료된 로그인 세션으로 새 연결을 허용했다")
        assert caught.value.status_code == 401
    async with agent_sessions() as db:
        turn = await db.scalar(select(InterviewTurn).where(InterviewTurn.turn_no == 9))
        assert turn.answer_text == "팀원 담당입니다" and turn.analysis is not None
        assert (await db.get(InterviewSession, agent_seed["interview_id"])).status == "completed"


@pytest.mark.parametrize("phase", ["answer_analysis", "next_question"])
async def test_takeover_waits_for_the_accepted_answer_without_repeating_model_work(
    agent_sessions, agent_seed, connect_ws, monkeypatch, phase
):
    from app.features.interview import director_service

    entered, release = threading.Event(), threading.Event()
    requests = []
    turn_no = 9 if phase == "answer_analysis" else 1
    await seed_turns(agent_sessions, agent_seed, turn_no)

    async def pause():
        entered.set()
        assert await asyncio.to_thread(release.wait, 10), "검사 중인 모델 대기를 해제하지 않았다"

    start = director_service.start_director

    async def next_question(*args, **kwargs):
        await pause()
        return await start(*args, **kwargs)

    if phase == "next_question":
        monkeypatch.setattr(director_service, "start_director", next_question)

    async def handle(request):
        payload = json.loads(json.loads(request.content)["input"][0]["content"][0]["text"])
        requests.append(payload.get("operation", "analysis"))
        if payload.get("operation") == "review":
            return response(
                dict.fromkeys(
                    [
                        "plan_valid",
                        "context_valid",
                        "wording_valid",
                        "contract_matches",
                        "safe_alternative",
                    ],
                    True,
                )
                | {"reason_summary": "적합"}
            )
        if payload.get("operation") == "plan":
            return response(
                {
                    "question": {
                        "persona": payload["context"]["allowed_personas"][0],
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
        if phase == "answer_analysis":
            await pause()
        return response(asdict(analysis()))

    with connect_ws(handle) as (client, _, path, _, _):
        with client.websocket_connect(path, headers={"origin": "http://localhost:5173"}) as old:
            assert old.receive_json()["turn"] == turn_no
            old.send_json({"type": "answer", "turn": turn_no, "text": "팀원 담당입니다"})
            assert old.receive_json() == {"type": "answerReceived"}
            assert old.receive_json() == {"type": "thinking"}
            assert entered.wait(5)
            try:
                with client.websocket_connect(
                    path, headers={"origin": "http://localhost:5173"}
                ) as new:
                    with pytest.raises(WebSocketDisconnect):
                        old.receive_json()
                    with ThreadPoolExecutor(max_workers=1) as pool:
                        message = pool.submit(new.receive_json)
                        try:
                            with pytest.raises(FutureTimeout):
                                message.result(timeout=0.2)
                        finally:
                            release.set()
                        event = message.result(timeout=10)
                    if turn_no == 9:
                        assert event == {"type": "interviewEnd"}
                    else:
                        assert event["type"] == "question" and event["turn"] == 2
            finally:
                release.set()
    async with agent_sessions() as db:
        answered = await db.scalar(select(InterviewTurn).where(InterviewTurn.turn_no == turn_no))
        assert answered.answer_text == "팀원 담당입니다" and answered.analysis is not None
        turns = list(await db.scalars(select(InterviewTurn)))
        assert len(turns) == (9 if turn_no == 9 else 2)
    assert requests == (["analysis"] if turn_no == 9 else ["analysis", "plan", "review"])


async def test_third_connection_waits_until_the_middle_socket_has_actually_closed(
    agent_sessions, agent_seed, connect_ws, monkeypatch
):
    await seed_turns(agent_sessions, agent_seed, 9)
    model_entered, model_release = threading.Event(), threading.Event()
    close_entered, close_release, accepted = (threading.Event() for _ in range(3))
    original_close = WebSocket.close

    async def close(socket, *args, **kwargs):
        if socket.headers.get("x-test-connection") == "middle":
            close_entered.set()
            assert await asyncio.to_thread(close_release.wait, 10)
        await original_close(socket, *args, **kwargs)

    monkeypatch.setattr(WebSocket, "close", close)

    async def model(request):
        model_entered.set()
        assert await asyncio.to_thread(model_release.wait, 10)
        return response(asdict(analysis()))

    with connect_ws(model) as (client, _, path, _, _):
        with client.websocket_connect(path, headers={"origin": "http://localhost:5173"}) as old:
            old.receive_json()
            old.send_json({"type": "answer", "turn": 9, "text": "팀원 담당입니다"})
            assert old.receive_json() == {"type": "answerReceived"}
            assert old.receive_json() == {"type": "thinking"}
            assert model_entered.wait(5)
            try:
                with client.websocket_connect(
                    path,
                    headers={"origin": "http://localhost:5173", "x-test-connection": "middle"},
                ):

                    def third():
                        with client.websocket_connect(
                            path, headers={"origin": "http://localhost:5173"}
                        ) as socket:
                            accepted.set()
                            return socket.receive_json()

                    with ThreadPoolExecutor(max_workers=1) as pool:
                        final = pool.submit(third)
                        try:
                            assert close_entered.wait(5)
                            assert not accepted.wait(0.2), (
                                "기존 소켓이 닫히기 전에 새 연결을 수락했다"
                            )
                            close_release.set()
                            assert accepted.wait(5)
                        finally:
                            close_release.set()
                            model_release.set()
                        assert final.result(timeout=10) == {"type": "interviewEnd"}
            finally:
                close_release.set()
                model_release.set()


@pytest.mark.parametrize("error", [OSError, RuntimeError, WebSocketDisconnect])
async def test_failed_ack_delivery_preserves_answer_and_finishes_analysis_once(
    agent_sessions,
    agent_seed,
    connect_ws,
    monkeypatch,
    error,
):
    await seed_turns(agent_sessions, agent_seed, 9)
    original = WebSocket.send_json
    sent = []
    acknowledged = threading.Event()

    async def fail_ack(socket, data, mode="text"):
        if data.get("type") == "answerReceived":
            acknowledged.set()
            raise error("connection lost")
        await original(socket, data, mode=mode)

    monkeypatch.setattr(WebSocket, "send_json", fail_ack)

    def model(request):
        sent.append(request)
        return response(asdict(analysis()))

    with connect_ws(model) as (client, _, path, _, _):
        with client.websocket_connect(path, headers={"origin": "http://localhost:5173"}) as socket:
            assert socket.receive_json()["turn"] == 9
            socket.send_json({"type": "answer", "turn": 9, "text": "팀원 담당입니다"})
            assert acknowledged.wait(5)
        with pytest.raises(WebSocketDenialResponse) as caught:
            with client.websocket_connect(path, headers={"origin": "http://localhost:5173"}):
                pytest.fail("완료된 면접 연결을 수락했다")
        assert caught.value.status_code == 409
        snapshot = client.get(
            f"/api/interviews/{agent_seed['interview_id']}",
            headers={"origin": "http://localhost:5173"},
        )
        assert snapshot.status_code == 200 and snapshot.json()["status"] == "completed"
    assert len(sent) == 1
    async with agent_sessions() as db:
        turn = await db.scalar(select(InterviewTurn).where(InterviewTurn.turn_no == 9))
        assert turn.answer_text == "팀원 담당입니다" and turn.analysis is not None
        assert (await db.get(InterviewSession, agent_seed["interview_id"])).status == "completed"


async def test_evidence_check_is_sent_only_after_actual_evidence_is_committed(
    agent_sessions,
    agent_seed,
    connect_ws,
):
    await seed_turns(agent_sessions, agent_seed, 9)
    sha = agent_seed["sha"]
    root, src = "b" * 40, "c" * 40
    blob = "ce013625030ba8dba906f756967f9e9ca394464a"
    base = "/repos/owner/sample"
    github = {
        base: {"id": 123, "full_name": "owner/sample", "private": False, "visibility": "public"},
        f"{base}/git/commits/{sha}": {"sha": sha, "tree": {"sha": root}},
        f"{base}/git/trees/{root}": {
            "sha": root,
            "truncated": False,
            "tree": [{"path": "src", "type": "tree", "mode": "040000", "sha": src}],
        },
        f"{base}/git/trees/{src}": {
            "sha": src,
            "truncated": False,
            "tree": [{"path": "main.py", "type": "blob", "mode": "100644", "sha": blob}],
        },
        f"{base}/contents/src/main.py": {
            "path": "src/main.py",
            "type": "file",
            "encoding": "base64",
            "size": 6,
            "sha": blob,
            "content": "aGVsbG8K\n",
        },
    }
    initial = replace(
        analysis(),
        needs_verification=True,
        verification_requests=(
            c.VerificationRequest(
                "팀원 담당입니다",
                "현재 구현 확인",
                str(agent_seed["repo_id"]),
                sha,
                ("src/main.py",),
            ),
        ),
    )

    def model(request):
        if request.url.host == "api.github.com":
            return httpx.Response(200, json=github[request.url.path])
        payload = json.loads(json.loads(request.content)["input"][0]["content"][0]["text"])
        return response(asdict(analysis() if payload["tool_results"] else initial))

    with connect_ws(model) as (client, _, path, _, _):
        with client.websocket_connect(path, headers={"origin": "http://localhost:5173"}) as socket:
            socket.receive_json()
            socket.send_json({"type": "answer", "turn": 9, "text": "팀원 담당입니다"})
            assert socket.receive_json() == {"type": "answerReceived"}
            assert socket.receive_json() == {"type": "thinking"}
            assert socket.receive_json() == {
                "type": "evidenceCheck",
                "repository": "sample",
                "file": "src/main.py",
            }

            async def stored():
                async with agent_sessions() as db:
                    row = await db.scalar(select(Evidence))
                    return row.snippet, row.git_ref

            assert client.portal.call(stored) == ("hello\n", sha)
            assert socket.receive_json() == {"type": "interviewEnd"}
