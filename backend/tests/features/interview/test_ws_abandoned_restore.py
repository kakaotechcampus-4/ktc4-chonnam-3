"""중단 알림이 유실되어도 DB의 종료 상태가 이전 질문 재전달을 막는다."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from app.features.interview import ws


async def test_abandoned_restore_closes_without_caching_or_resending(monkeypatch):
    socket = SimpleNamespace(close=AsyncMock(), send_json=AsyncMock())
    redis = SimpleNamespace(exists=AsyncMock(return_value=0))
    connection = ws._Connection(socket, redis, "session", uuid4(), b"raw", "nonce")
    read = AsyncMock(
        return_value=SimpleNamespace(
            status="abandoned",
            question={"type": "question", "text": "previous"},
            snapshot={"status": "abandoned"},
        )
    )
    execute = AsyncMock(return_value=1)
    monkeypatch.setattr(ws, "_read_state", read)
    monkeypatch.setattr(ws, "_script", execute)

    assert await connection.restore(uuid4()) is False
    assert connection.closed.is_set()
    socket.close.assert_awaited_once_with(code=1000)
    socket.send_json.assert_not_awaited()
    assert execute.await_count == 1
    assert execute.await_args.args[1] == ws._RELEASE
