"""run_progress_response() — EventSourceResponse 로 감싸는 어댑터 (task-12)."""

import anyio
from sse_starlette.sse import EventSourceResponse
from starlette.types import Message

from app.realtime.sse import KEEPALIVE_SECONDS, run_progress_response


async def _events():
    yield {"event": "step", "data": "{}"}


def test_wraps_events_in_event_source_response() -> None:
    response = run_progress_response(_events())

    assert isinstance(response, EventSourceResponse)


def test_sets_keepalive_ping_interval() -> None:
    response = run_progress_response(_events())

    assert response.ping_interval == KEEPALIVE_SECONDS


def test_sets_anti_buffering_headers() -> None:
    """SSE 는 프록시·CDN 버퍼링에 죽는다 — 헤더로 명시적으로 막는다(docs/pipeline.md 3절)."""
    response = run_progress_response(_events())

    assert response.headers.get("x-accel-buffering") == "no"
    assert response.headers.get("cache-control") == "no-store"


async def test_closes_event_generator_when_client_disconnects_during_send() -> None:
    """send() 대기 중 접속이 끊겨도 응답 종료 시 생성기(=Redis 구독)가 닫혀야 한다."""
    finalized: list[bool] = []

    async def events():
        try:
            yield {"event": "step", "data": "{}"}
            await anyio.sleep_forever()
        finally:
            finalized.append(True)

    response = run_progress_response(events())  # 강한 참조를 유지해 GC 정리에 기대지 못하게 한다
    body_send_started = anyio.Event()

    async def receive() -> Message:
        await body_send_started.wait()
        return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        if message["type"] == "http.response.body":
            body_send_started.set()
            await anyio.sleep_forever()  # 느린 클라이언트: 전송이 끝나지 않는다

    with anyio.fail_after(5):
        await response({"type": "http", "method": "GET", "headers": []}, receive, send)

    assert finalized == [True]


async def test_closes_event_generator_on_normal_completion() -> None:
    finalized: list[bool] = []

    async def events():
        try:
            yield {"event": "step", "data": "{}"}
        finally:
            finalized.append(True)

    response = run_progress_response(events())

    async def receive() -> Message:
        await anyio.sleep_forever()
        raise AssertionError("unreachable")

    async def send(message: Message) -> None:
        return None

    with anyio.fail_after(5):
        await response({"type": "http", "method": "GET", "headers": []}, receive, send)

    assert finalized == [True]
