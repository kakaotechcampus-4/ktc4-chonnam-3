"""sse-starlette 어댑터.

docs/pipeline.md 3절 / task-12
"""

from collections.abc import AsyncIterator
from typing import Any

import anyio
from sse_starlette.sse import EventSourceResponse
from starlette.types import Receive, Scope, Send

# 15초 주기 keep-alive comment(`: ping`). CDN/프록시 버퍼링에 죽지 않게 한다.
KEEPALIVE_SECONDS = 15


class _ClosingEventSourceResponse(EventSourceResponse):
    """응답이 끝나면 이벤트 생성기를 명시적으로 닫는 EventSourceResponse.

    sse-starlette 는 `send()` 대기 중 접속이 끊겨 취소되면 body_iterator 를 닫지 않는다.
    생성기가 GC 될 때까지 `subscribe()` 의 finally 에 진입하지 못해 Redis 연결이 풀에
    반환되지 않으므로, 응답 종료 시점에 직접 닫는다.
    """

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            # 접속 종료로 취소가 걸린 상태에서도 정리는 끝까지 수행한다.
            with anyio.CancelScope(shield=True):
                aclose = getattr(self.body_iterator, "aclose", None)
                if aclose is not None:
                    await aclose()


def run_progress_response(events: AsyncIterator[dict[str, Any]]) -> EventSourceResponse:
    """SSE 이벤트 스트림을 HTTP 응답으로 감싼다.

    입력: dict payload 스트림(features/analysis/events.stream_run_progress 의 출력).
    출력: EventSourceResponse.

    ⚠ SSE 는 프록시·CDN 에서 버퍼링되면 죽는다 — `X-Accel-Buffering: no` 와
    `Cache-Control: no-store` 를 응답 헤더에 넣는다(docs/pipeline.md 3절, docs/deploy.md 3절 ③).
    CloudFront 쪽 자동 압축 해제는 배포 설정(task-17)이 맡는다.
    """
    return _ClosingEventSourceResponse(
        events,
        ping=KEEPALIVE_SECONDS,
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-store"},
    )
