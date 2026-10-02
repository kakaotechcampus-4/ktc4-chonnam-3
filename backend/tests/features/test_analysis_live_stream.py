"""실제 SSE 라우터와 ARQ를 함께 실행해 종료 시점의 DB 조회·유실 복구를 확인한다."""

import asyncio
import json
from time import monotonic
from uuid import UUID

import httpx
import pytest

from app.db.models.analysis import AnalysisJob
from tests.features.test_analysis_api import member as member
from tests.features.test_analysis_worker import (
    _drain,
    _http_handler,
    _start,
)
from tests.features.test_analysis_worker import (
    app_settings as app_settings,
)
from tests.features.test_analysis_worker import (
    repositories as repositories,
)


@pytest.mark.parametrize("lose_notifications", [False, True])
@pytest.mark.parametrize("posting_failed", [False, True])
async def test_live_sse_terminal_is_visible_to_rest_and_recovers_lost_notifications(
    client, app, repositories, monkeypatch, record_property, lose_notifications, posting_failed
):
    run_id = await _start(client)
    if lose_notifications:
        pipeline = app.state.redis.pipeline

        def disconnected_pipeline(*args, **kwargs):
            pipe = pipeline(*args, **kwargs)
            publish, execute = pipe.publish, pipe.execute
            notification = False

            def mark_notification(*args, **kwargs):
                nonlocal notification
                notification = True
                return publish(*args, **kwargs)

            async def disconnected():
                if notification:
                    raise ConnectionError("notification connection lost")
                return await execute()

            # 실제 큐·구독 연결은 유지하고, 워커의 알림 전송 경계만 실패시킨다.
            pipe.publish, pipe.execute = mark_notification, disconnected
            return pipe

        monkeypatch.setattr(app.state.redis, "pipeline", disconnected_pipeline)

    ready = asyncio.Event()
    disconnected = asyncio.Event()
    messages, arrivals = [], []
    observations = {}
    request_sent = False
    pending = b""

    async def receive():
        nonlocal request_sent
        if not request_sent:
            request_sent = True
            return {"type": "http.request", "body": b"", "more_body": False}
        await disconnected.wait()
        return {"type": "http.disconnect"}

    async def send(message):
        nonlocal pending
        if message["type"] == "http.response.start":
            observations["http_status"] = message["status"]
            observations["headers"] = dict(message["headers"])
            if message["status"] != 200:
                ready.set()
            return
        pending += message.get("body", b"")
        while b"\r\n\r\n" in pending:
            block, pending = pending.split(b"\r\n\r\n", 1)
            data = [line[6:] for line in block.split(b"\r\n") if line.startswith(b"data: ")]
            if not data:
                continue
            assert not any(line.startswith(b"event:") for line in block.split(b"\r\n"))
            payload = json.loads(b"\n".join(data))
            messages.append(payload)
            arrivals.append(monotonic())
            # 최초 단계 수신은 Redis 구독이 성립하고 DB 상태까지 읽었다는 뜻이다.
            ready.set()
            if payload["type"] in {"completed", "failed"}:
                # 워커 전체 종료를 기다리지 않고 실제 SSE 전송 시점에 별도 조회한다.
                observations["status"] = await client.get(f"/api/analysis-runs/{run_id}")
                observations["result"] = await client.get(f"/api/analysis-runs/{run_id}/result")
                async with app.state.session_factory() as session:
                    saved = await session.get(AnalysisJob, UUID(run_id))
                    observations["db_status"] = saved.status
                    observations["db_steps"] = {s["key"]: s["status"] for s in saved.steps}
                observations["mirror"] = await app.state.redis.hgetall(f"run:{run_id}:steps")

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": f"/api/analysis-runs/{run_id}/events",
        "raw_path": f"/api/analysis-runs/{run_id}/events".encode(),
        "root_path": "",
        "query_string": b"",
        "headers": [
            (key.lower(), value)
            for key, value in client.build_request(
                "GET", f"/api/analysis-runs/{run_id}/events"
            ).headers.raw
        ],
        "client": ("127.0.0.1", 12345),
        "server": ("localhost", 5173),
    }
    handler, _ = _http_handler(posting_failed=posting_failed)
    # ASGITransport는 응답을 끝까지 모으므로 ASGI send에서 각 SSE 프레임을 관찰한다.
    stream = asyncio.create_task(app(scope, receive, send))
    try:
        async with asyncio.timeout(20):
            await ready.wait()
            assert observations["http_status"] == 200
            started = monotonic()
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
                await _drain(app, http)
            worker_finished = monotonic()
            await stream
    finally:
        disconnected.set()
        if not stream.done():
            stream.cancel()
        await asyncio.gather(stream, return_exceptions=True)

    assert observations["http_status"] == 200
    assert observations["headers"][b"x-accel-buffering"] == b"no"
    assert messages[-1] == (
        {"type": "failed", "reason": "jd_fetch_failed"} if posting_failed else {"type": "completed"}
    )
    assert observations["db_status"] == ("failed" if posting_failed else "succeeded")
    assert observations["status"].status_code == 200
    assert observations["status"].json()["status"] == ("failed" if posting_failed else "completed")
    if posting_failed:
        assert observations["status"].json()["failureReason"] == "jd_fetch_failed"
        assert observations["result"].status_code == 409
        assert observations["result"].json()["error"]["reason"] == "not_ready"
    else:
        assert observations["result"].status_code == 200
        assert observations["result"].json()["analyzedCount"] == 5
    step_events = [m for m in messages if m["type"] == "step"]
    assert all("key" in m and "step" not in m for m in step_events)
    final_steps = {m["key"]: m["status"] for m in step_events}
    assert final_steps == {
        "doc_extract": "skipped",
        "repo_select": "completed",
        "repo_detail": "completed",
        "jd_fetch": "failed" if posting_failed else "completed",
        "jd_extract": "skipped" if posting_failed else "completed",
        "repo_analyze": "skipped" if posting_failed else "completed",
        "match_score": "skipped" if posting_failed else "completed",
    }
    assert final_steps == observations["db_steps"]
    if lose_notifications:
        assert observations["mirror"] == {}
    else:
        assert {"type": "step", "key": "repo_detail", "status": "running"} in step_events
        assert {k.decode(): v.decode() for k, v in observations["mirror"].items()} == final_steps
    record_property("notifications_lost", lose_notifications)
    record_property("posting_failed", posting_failed)
    record_property("worker_seconds", round(worker_finished - started, 3))
    record_property(
        "terminal_after_worker_seconds", round(max(0, arrivals[-1] - worker_finished), 3)
    )
