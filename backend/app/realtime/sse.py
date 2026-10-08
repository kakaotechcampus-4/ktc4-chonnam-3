"""sse-starlette 어댑터.

docs/pipeline.md 3절 / task-12
"""

from collections.abc import AsyncIterator
from typing import Any

from sse_starlette.sse import EventSourceResponse

# 15초 주기 keep-alive comment(`: ping`). CDN/프록시 버퍼링에 죽지 않게 한다.
KEEPALIVE_SECONDS = 15


def run_progress_response(events: AsyncIterator[dict[str, Any]]) -> EventSourceResponse:
    """SSE 이벤트 스트림을 HTTP 응답으로 감싼다.

    입력: dict payload 스트림(features/analysis/events.stream_run_progress 의 출력).
    출력: EventSourceResponse.

    ⚠ SSE 는 프록시·CDN 에서 버퍼링되면 죽는다 — `X-Accel-Buffering: no` 와
    `Cache-Control: no-store` 를 응답 헤더에 넣는다(docs/pipeline.md 3절, docs/deploy.md 3절 ③).
    CloudFront 쪽 자동 압축 해제는 배포 설정(task-17)이 맡는다.
    """
    return EventSourceResponse(
        events,
        ping=KEEPALIVE_SECONDS,
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-store"},
    )
