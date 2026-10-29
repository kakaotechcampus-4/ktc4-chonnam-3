"""실제 앱 WS가 DB 준비 진행을 복원하고 준비 중을 실패로 바꾸지 않는다."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from starlette.websockets import WebSocketDisconnect

from app.db.models import InterviewSession, InterviewTurn, LLMCallRecord
from tests.agents import test_director_ws
from tests.agents.test_director_runtime_service import seed_turns

connect_ws = test_director_ws.connect_ws

KEYS = ("analyze_repo", "build_persona", "set_criteria", "compose_question")


async def prepare_state(sessions, seed, statuses, *, status="preparing", error=None):
    async with sessions.begin() as db:
        interview = await db.get(InterviewSession, seed["interview_id"])
        interview.status = status
        interview.prepare_steps = [
            {"step": key, "status": value} for key, value in zip(KEYS, statuses, strict=True)
        ]
        interview.last_error = error


@pytest.fixture(autouse=True)
def quick_poll(monkeypatch):
    from app.features.interview import ws

    monkeypatch.setattr(ws, "_PREPARE_POLL_SECONDS", 0.01, raising=False)


async def test_preparing_streams_snapshot_changes_then_completion_and_stored_question(
    agent_sessions, agent_seed, connect_ws
):
    await prepare_state(agent_sessions, agent_seed, ["pending"] * 4)
    with connect_ws() as (client, _, path, _, _):
        with client.websocket_connect(path, headers={"origin": "http://localhost:5173"}) as socket:
            assert [socket.receive_json() for _ in range(4)] == [
                {"type": "prepareStep", "key": key, "status": "pending"} for key in KEYS
            ]
            client.portal.call(
                prepare_state,
                agent_sessions,
                agent_seed,
                ["completed", "running", "pending", "pending"],
            )
            assert socket.receive_json() == {
                "type": "prepareStep",
                "key": "analyze_repo",
                "status": "completed",
            }
            assert socket.receive_json() == {
                "type": "prepareStep",
                "key": "build_persona",
                "status": "running",
            }
            client.portal.call(seed_turns, agent_sessions, agent_seed)

            async def ready():
                await prepare_state(
                    agent_sessions, agent_seed, ["completed"] * 4, status="in_progress"
                )

            client.portal.call(ready)
            assert [socket.receive_json() for _ in range(3)] == [
                {"type": "prepareStep", "key": key, "status": "completed"} for key in KEYS[1:]
            ]
            assert socket.receive_json() == {"type": "prepareCompleted"}
            assert socket.receive_json() == {
                "type": "question",
                "persona": "hr_manager",
                "text": "본인의 역할을 설명해 주세요.",
                "turn": 1,
            }


async def test_preparing_reconnect_reads_current_steps_without_restarting_work(
    agent_sessions, agent_seed, connect_ws
):
    await prepare_state(agent_sessions, agent_seed, ["completed", "running", "pending", "pending"])
    with connect_ws() as (client, _, path, _, _):
        for statuses in [
            ["completed", "running", "pending", "pending"],
            ["completed", "completed", "running", "pending"],
        ]:
            client.portal.call(prepare_state, agent_sessions, agent_seed, statuses)
            with client.websocket_connect(
                path, headers={"origin": "http://localhost:5173"}
            ) as socket:
                assert [socket.receive_json() for _ in range(4)] == [
                    {"type": "prepareStep", "key": key, "status": status}
                    for key, status in zip(KEYS, statuses, strict=True)
                ]
    async with agent_sessions() as db:
        assert await db.scalar(select(LLMCallRecord.id)) is None


async def test_preparing_rejects_answers_without_saving_or_calling_a_model(
    agent_sessions, agent_seed, connect_ws
):
    await prepare_state(agent_sessions, agent_seed, ["pending"] * 4)
    with connect_ws() as (client, _, path, _, _):
        with client.websocket_connect(path, headers={"origin": "http://localhost:5173"}) as socket:
            for _ in range(4):
                assert socket.receive_json()["type"] == "prepareStep"
            socket.send_json({"type": "answer", "turn": 1, "text": "아직 준비 중"})
            assert socket.receive_json()["reason"] == "answer_rejected"
    async with agent_sessions() as db:
        assert await db.scalar(select(InterviewTurn.id)) is None
        assert await db.scalar(select(LLMCallRecord.id)) is None


async def test_preparing_failure_delivers_committed_stage_and_original_error(
    agent_sessions, agent_seed, connect_ws
):
    await prepare_state(agent_sessions, agent_seed, ["pending"] * 4)
    saved_error = dict(
        reason="repo_analyze_failed",
        code="ERR_REPO_ANALYZE_FAILED",
        step="analyze_repo",
        recoverable=True,
        occurredAt=datetime.now(UTC).isoformat(),
    )
    with connect_ws() as (client, _, path, _, _):
        with client.websocket_connect(path, headers={"origin": "http://localhost:5173"}) as socket:
            for _ in range(4):
                assert socket.receive_json()["type"] == "prepareStep"

            async def fail():
                await prepare_state(
                    agent_sessions,
                    agent_seed,
                    ["failed", "pending", "pending", "pending"],
                    status="preparing_failed",
                    error=saved_error,
                )

            client.portal.call(fail)
            assert socket.receive_json() == {
                "type": "prepareStep",
                "key": "analyze_repo",
                "status": "failed",
            }
            event = socket.receive_json()
            assert event["type"] == "error" and event["reason"] == "repo_analyze_failed"
            assert event["step"] == "analyze_repo" and event["code"] == saved_error["code"]
            with pytest.raises(WebSocketDisconnect) as closed:
                socket.receive_json()
            assert closed.value.code == 1000


async def test_missing_llm_settings_keeps_stale_validation_and_logs_configuration_fields(
    agent_sessions, agent_seed, connect_ws, caplog
):
    await seed_turns(agent_sessions, agent_seed)
    with connect_ws() as (client, app, path, _, _):
        app.state.settings = app.state.settings.model_copy(update={"llm_timeout_seconds": None})
        with client.websocket_connect(path, headers={"origin": "http://localhost:5173"}) as socket:
            assert socket.receive_json()["turn"] == 1
            socket.send_json({"type": "answer", "turn": 2, "text": "오래된 턴"})
            assert socket.receive_json()["reason"] == "answer_stale_turn"
            socket.send_json({"type": "answer", "turn": 1, "text": "답변"})
            assert socket.receive_json()["reason"] == "question_failed"
            with pytest.raises(WebSocketDisconnect) as closed:
                socket.receive_json()
            assert closed.value.code == 1011
    output = caplog.text
    assert "interview_ws_llm_configuration_invalid" in output
    assert "llm_timeout_seconds" in output and "fixture-key" not in output
    async with agent_sessions() as db:
        assert (await db.scalar(select(InterviewTurn))).answer_text is None
        assert await db.scalar(select(LLMCallRecord.id)) is None


async def test_existing_preparation_failure_replays_only_the_stored_error(
    agent_sessions, agent_seed, connect_ws
):
    error = dict(
        reason="criteria_set_failed",
        code="ERR_CRITERIA_SET_FAILED",
        step="set_criteria",
        recoverable=True,
        occurredAt=datetime.now(UTC).isoformat(),
    )
    await prepare_state(
        agent_sessions,
        agent_seed,
        ["completed", "completed", "failed", "pending"],
        status="preparing_failed",
        error=error,
    )
    with connect_ws() as (client, _, path, _, _):
        with client.websocket_connect(path, headers={"origin": "http://localhost:5173"}) as socket:
            event = socket.receive_json()
            assert event["type"] == "error" and event["reason"] == "criteria_set_failed"
            assert event["step"] == "set_criteria" and event["code"] == error["code"]
            with pytest.raises(WebSocketDisconnect) as closed:
                socket.receive_json()
            assert closed.value.code == 1000
