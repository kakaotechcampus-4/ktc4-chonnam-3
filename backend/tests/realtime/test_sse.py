"""run_progress_response() — EventSourceResponse 로 감싸는 어댑터 (task-12)."""

from sse_starlette.sse import EventSourceResponse

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
