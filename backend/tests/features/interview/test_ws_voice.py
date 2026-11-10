"""음성 답변 WS 처리(answerStart·청크·answerEnd). Postgres·Redis 없이 연결을 가짜로 둔다."""

import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import WebSocketDisconnect

from app.features.interview import ws
from app.features.interview.agent_context import AgentStateError
from app.features.interview.answer_audio import (
    AnswerAudioBuffer,
    AnswerAudioLimits,
    AnswerEnd,
    AnswerStart,
)
from app.features.interview.director_service import AnswerExecution
from app.integrations.stt.client import SttError, SttFailureCause

SECRET = "stt-secret-key"
USER_ID = uuid4()


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class FakeStt:
    def __init__(self, result: str | Exception) -> None:
        self.result = result
        self.calls: list[tuple[bytes, str]] = []

    async def transcribe(self, audio: bytes, mime: str) -> str:
        self.calls.append((audio, mime))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class FakeConnection:
    def __init__(self, stt: object, settings: object | None = None) -> None:
        self.interview_id = uuid4()
        state = SimpleNamespace(
            settings=settings or SimpleNamespace(answer_audio_max_seconds=180.0),
            stt_client=stt,
        )
        self.socket = SimpleNamespace(app=SimpleNamespace(state=state))
        self.events: list[dict] = []
        self.closed = False

    async def send(self, event: dict) -> None:
        self.events.append(event)

    async def restore(self, user_id) -> bool:
        self.events.append({"type": "restored"})
        return True

    async def close(self, code: int = 1000) -> None:
        self.closed = True

    @property
    def types(self) -> list[str]:
        return [event["type"] for event in self.events]


def _buffer(clock: Clock | None = None, max_bytes: int = 1000) -> AnswerAudioBuffer:
    return AnswerAudioBuffer(AnswerAudioLimits(max_bytes, 180.0, 5.0, 10.0), clock or Clock())


@pytest.fixture
def executed(monkeypatch):
    """`_execute`를 대체한다. 저장 성공이면 answerReceived·thinking을 보낸 것처럼 기록한다."""
    calls: list[tuple[int, str]] = []
    outcome: dict = {"raise": None}

    async def fake(connection, user_id, turn, text, *, answer_mode):
        assert answer_mode in {"voice", "text"}
        calls.append((turn, text))
        if outcome["raise"] is not None:
            raise outcome["raise"]
        await connection.send({"type": "answerReceived"})
        await connection.send({"type": "thinking"})
        return AnswerExecution(uuid4(), None, None, False, None, None, True)

    monkeypatch.setattr(ws, "_execute", fake)
    _patch_state(monkeypatch, current_turn=3, answerable=3)
    return SimpleNamespace(calls=calls, outcome=outcome)


async def _answer(connection, buffer, turn=3, chunks=(b"abc", b"def")):
    buffer.start(turn, "audio/webm;codecs=opus")
    for chunk in chunks:
        buffer.append(chunk)
    return await ws._answer_end(connection, USER_ID, buffer, AnswerEnd(turn))


async def test_message_order_is_transcript_then_answer_received_then_thinking(executed):
    stt = FakeStt("직접 설계했습니다.")
    connection = FakeConnection(stt)

    assert await _answer(connection, _buffer()) is True

    assert connection.types == ["transcript", "answerReceived", "thinking", "restored"]
    assert connection.events[0] == {"type": "transcript", "turn": 3, "text": "직접 설계했습니다."}
    assert stt.calls == [(b"abcdef", "audio/webm;codecs=opus")]
    assert executed.calls == [(3, "직접 설계했습니다.")]


async def test_empty_transcript_sends_stt_failed_with_cause_and_saves_nothing(executed):
    connection = FakeConnection(FakeStt(SttError(SttFailureCause.EMPTY_TRANSCRIPT)))

    assert await _answer(connection, _buffer()) is True

    (event,) = connection.events
    assert event["reason"] == "stt_failed"
    assert event["code"] == "ERR_STT_FAILED"
    assert event["recoverable"] is True
    assert event["step"] is None
    assert event["details"] == {"cause": "empty_transcript"}
    assert executed.calls == []


@pytest.mark.parametrize(
    "cause",
    [
        SttFailureCause.TIMEOUT,
        SttFailureCause.PROVIDER_ERROR,
        SttFailureCause.INVALID_AUDIO,
        SttFailureCause.INVALID_RESPONSE,
        SttFailureCause.AUDIO_TOO_LARGE,
    ],
)
async def test_other_stt_failures_omit_details_and_leak_nothing(executed, cause, caplog):
    connection = FakeConnection(FakeStt(SttError(cause)))

    with caplog.at_level("DEBUG"):
        await _answer(connection, _buffer())

    (event,) = connection.events
    assert event["reason"] == "stt_failed"
    assert "details" not in event
    assert set(event) == set(ws._error("stt_failed"))
    assert SECRET not in caplog.text
    assert executed.calls == []


async def test_unauthorized_stt_is_unrecoverable_with_cause(executed, caplog):
    connection = FakeConnection(FakeStt(SttError(SttFailureCause.UNAUTHORIZED)))

    with caplog.at_level("DEBUG"):
        assert await _answer(connection, _buffer()) is True

    (event,) = connection.events
    assert event["reason"] == "stt_failed"
    assert event["recoverable"] is False
    assert event["details"] == {"cause": "stt_unavailable"}
    assert SECRET not in caplog.text
    assert executed.calls == []


async def test_missing_stt_configuration_is_unrecoverable_without_values(executed, caplog):
    settings = SimpleNamespace(
        answer_audio_max_seconds=180.0,
        require_stt=lambda: (_ for _ in ()).throw(ValueError(f"bad {SECRET}")),
    )
    connection = FakeConnection(None, settings)

    with caplog.at_level("DEBUG"):
        await _answer(connection, _buffer())

    (event,) = connection.events
    assert event["reason"] == "stt_failed"
    assert event["recoverable"] is False
    assert event["details"] == {"cause": "stt_unavailable"}
    assert SECRET not in caplog.text


async def test_answer_end_without_start_is_answer_rejected(executed):
    stt = FakeStt("unused")
    connection = FakeConnection(stt)

    assert await ws._answer_end(connection, USER_ID, _buffer(), AnswerEnd(3)) is True

    assert connection.types == ["error"]
    assert connection.events[0]["reason"] == "answer_rejected"
    assert stt.calls == [] and executed.calls == []


async def test_answer_end_for_another_turn_is_rejected_and_keeps_active_audio(executed):
    buffer = _buffer()
    buffer.start(3, "audio/webm")
    connection = FakeConnection(FakeStt("unused"))

    await ws._answer_end(connection, USER_ID, buffer, AnswerEnd(4))

    assert connection.events[0]["reason"] == "answer_rejected"
    assert buffer.active_turn == 3


async def test_save_failure_sends_answer_rejected_after_transcript_without_answer_received(
    executed,
):
    executed.outcome["raise"] = AgentStateError("answer_turn_invalid")
    connection = FakeConnection(FakeStt("답변"))

    assert await _answer(connection, _buffer()) is True

    assert connection.types == ["transcript", "error"]
    assert connection.events[1]["reason"] == "answer_rejected"


async def test_text_answer_keeps_stale_turn_reason(executed):
    executed.outcome["raise"] = AgentStateError("answer_turn_invalid")
    connection = FakeConnection(None)

    assert await ws._run_answer(connection, USER_ID, 1, "text", "answer_stale_turn") is True

    assert connection.events[0]["reason"] == "answer_stale_turn"


async def test_other_save_errors_close_the_connection(executed):
    executed.outcome["raise"] = AgentStateError("call_in_progress")
    connection = FakeConnection(FakeStt("답변"))

    assert await _answer(connection, _buffer()) is False

    assert connection.events[-1]["reason"] == "question_failed"
    assert connection.closed is True


async def test_audio_over_180_seconds_is_too_long_and_same_turn_can_restart(executed):
    clock = Clock()
    buffer = _buffer(clock)
    stt = FakeStt("재시도 답변")
    connection = FakeConnection(stt)

    buffer.start(3, "audio/webm")
    clock.now += 186.0
    await ws._answer_chunk(connection, buffer, b"late")

    (event,) = connection.events
    assert event["reason"] == "answer_too_long"
    assert event["code"] == "ERR_ANSWER_TOO_LONG"
    assert event["details"] == {"cause": "audio_too_long", "limitSeconds": 180}
    assert buffer.active_turn is None

    connection.events.clear()
    await _answer(connection, buffer)  # 같은 턴 answerStart로 다시 시작할 수 있다.
    assert connection.types[0] == "transcript"


async def test_audio_over_byte_limit_is_too_long(executed):
    buffer = _buffer(max_bytes=5)
    connection = FakeConnection(FakeStt("unused"))
    buffer.start(3, "audio/webm")

    await ws._answer_chunk(connection, buffer, b"123456")

    assert connection.events[0]["details"]["cause"] == "audio_too_long"
    assert buffer.active_turn is None


async def test_answer_end_after_the_time_limit_is_too_long(executed):
    clock = Clock()
    buffer = _buffer(clock)
    connection = FakeConnection(FakeStt("unused"))
    buffer.start(3, "audio/webm")
    buffer.append(b"abc")
    clock.now += 186.0

    await ws._answer_end(connection, USER_ID, buffer, AnswerEnd(3))

    assert connection.events[0]["reason"] == "answer_too_long"
    assert executed.calls == []


async def test_restart_on_same_turn_drops_the_unfinished_audio(executed, monkeypatch):
    buffer = _buffer()
    stt = FakeStt("새 답변")
    connection = FakeConnection(stt)
    _patch_state(monkeypatch, current_turn=3, answerable=3)

    await ws._answer_start(connection, USER_ID, buffer, AnswerStart(3, "audio/webm"))
    await ws._answer_chunk(connection, buffer, b"old")
    await ws._answer_start(connection, USER_ID, buffer, AnswerStart(3, "audio/webm"))
    await ws._answer_chunk(connection, buffer, b"new")
    await ws._answer_end(connection, USER_ID, buffer, AnswerEnd(3))

    assert stt.calls == [(b"new", "audio/webm")]


def _patch_state(monkeypatch, *, current_turn: int, answerable: int | None) -> None:
    async def read_state(socket, user_id, interview_id):
        question = {"turn": answerable} if answerable is not None else None
        return SimpleNamespace(
            status="in_progress",
            answer_mode="voice",
            question=question,
            snapshot={"currentTurn": current_turn},
        )

    monkeypatch.setattr(ws, "_read_state", read_state)


@pytest.mark.parametrize(
    ("turn", "current_turn", "answerable", "reason"),
    [
        (2, 3, 3, "answer_stale_turn"),  # 지나간 턴
        (4, 3, 3, "answer_rejected"),  # 아직 오지 않은 턴
        (3, 3, None, "answer_rejected"),  # 이미 답변이 저장된 현재 턴
    ],
)
async def test_answer_start_for_unanswerable_turn_is_rejected(
    monkeypatch, turn, current_turn, answerable, reason
):
    _patch_state(monkeypatch, current_turn=current_turn, answerable=answerable)
    buffer = _buffer()
    connection = FakeConnection(None)

    await ws._answer_start(connection, USER_ID, buffer, AnswerStart(turn, "audio/webm"))

    assert [event["reason"] for event in connection.events] == [reason]
    assert buffer.active_turn is None


async def test_connection_close_discards_unfinished_audio():
    buffer = _buffer()
    buffer.start(3, "audio/webm")
    buffer.append(b"abc")

    buffer.discard()  # 연결 종료 시 ws의 finally가 하는 일

    connection = FakeConnection(FakeStt("unused"))
    await ws._answer_end(connection, USER_ID, buffer, AnswerEnd(3))
    assert connection.events[0]["reason"] == "answer_rejected"


class FakeSocket:
    def __init__(self) -> None:
        self.queue: asyncio.Queue[dict] = asyncio.Queue()

    async def receive(self) -> dict:
        return await self.queue.get()


def _connection(socket: FakeSocket) -> ws._Connection:
    return ws._Connection(socket, None, "sid", uuid4(), b"raw", "nonce")  # type: ignore[arg-type]


async def test_receive_returns_text_as_json_and_binary_as_bytes():
    socket = FakeSocket()
    connection = _connection(socket)
    socket.queue.put_nowait({"type": "websocket.receive", "text": '{"type": "answerEnd"}'})
    socket.queue.put_nowait({"type": "websocket.receive", "bytes": b"\x00\x01"})

    assert await connection.receive() == {"type": "answerEnd"}
    assert await connection.receive() == b"\x00\x01"


async def test_receive_keeps_the_pending_frame_after_a_timeout():
    socket = FakeSocket()
    connection = _connection(socket)

    with pytest.raises(TimeoutError):
        await connection.receive(0.01)
    socket.queue.put_nowait({"type": "websocket.receive", "bytes": b"late"})

    assert await connection.receive(1) == b"late"  # 타임아웃으로 프레임을 잃지 않는다.
    await connection.release_receiver()


async def test_receive_raises_on_invalid_json_and_on_disconnect():
    socket = FakeSocket()
    connection = _connection(socket)
    socket.queue.put_nowait({"type": "websocket.receive", "text": "not json"})
    with pytest.raises(ValueError):
        await connection.receive()

    socket.queue.put_nowait({"type": "websocket.disconnect", "code": 1001})
    with pytest.raises(WebSocketDisconnect):
        await connection.receive()
