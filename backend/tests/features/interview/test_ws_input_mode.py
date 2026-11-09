"""저장된 세션 모드가 반대 입력의 전사·평가·저장 진입을 차단한다."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.features.interview import ws


@pytest.mark.parametrize(
    "mode,message",
    [
        ("voice", {"type": "answer", "turn": 1, "text": "직접 쓴 답변"}),
        ("text", {"type": "answerStart", "turn": 1, "mimeType": "audio/webm"}),
        ("text", {"type": "answerEnd", "turn": 1}),
        ("text", b"audio bytes"),
        ("unknown", {"type": "answer", "turn": 1, "text": "답변"}),
    ],
)
async def test_wrong_mode_is_rejected_before_any_answer_processing(monkeypatch, mode, message):
    connection = SimpleNamespace(send=AsyncMock())
    routes = [AsyncMock() for _ in range(4)]
    for name, route in zip(
        ("_answer_start", "_answer_end", "_answer_chunk", "_run_answer"), routes, strict=True
    ):
        monkeypatch.setattr(ws, name, route)

    assert await ws._handle_input(connection, uuid4(), None, message, mode) is True

    assert connection.send.await_args.args[0]["reason"] == "answer_rejected"
    assert connection.send.await_args.args[0]["recoverable"] is True
    assert all(route.await_count == 0 for route in routes)


async def test_legacy_text_keeps_the_original_answer_and_turn(monkeypatch):
    connection = SimpleNamespace(send=AsyncMock())
    run = AsyncMock(return_value=True)
    monkeypatch.setattr(ws, "_run_answer", run)
    user_id = uuid4()
    original = "  실제 제출한 문장\n두 번째 줄  "

    assert (
        await ws._handle_input(
            connection, user_id, None, {"type": "answer", "turn": 3, "text": original}, "text"
        )
        is True
    )

    run.assert_awaited_once_with(
        connection, user_id, 3, original, "answer_stale_turn", answer_mode="text"
    )
    connection.send.assert_not_awaited()


@pytest.mark.parametrize(
    "message,route",
    [
        ({"type": "answerStart", "turn": 1, "mimeType": "audio/webm"}, "_answer_start"),
        ({"type": "answerEnd", "turn": 1}, "_answer_end"),
        (b"audio bytes", "_answer_chunk"),
    ],
)
async def test_voice_messages_keep_the_existing_audio_route(monkeypatch, message, route):
    connection = SimpleNamespace(send=AsyncMock())
    operation = AsyncMock(return_value=True)
    monkeypatch.setattr(ws, route, operation)

    assert await ws._handle_input(connection, uuid4(), None, message, "voice") is True

    operation.assert_awaited_once()
    connection.send.assert_not_awaited()


def test_text_answer_parser_preserves_the_original_turn_and_whitespace():
    original = "  실제 제출한 문장\n두 번째 줄  "

    assert ws._answer({"type": "answer", "turn": 3, "text": original}) == (3, original)


@pytest.mark.parametrize(
    "message",
    [
        {"type": "answerStart", "turn": 1, "mimeType": "audio/webm"},
        {"type": "answerEnd", "turn": 1},
    ],
)
def test_text_answer_parser_rejects_voice_json_without_treating_it_as_an_answer(message):
    assert ws._answer(message) == "answer_rejected"
