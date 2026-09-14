"""structlog 설정, request_id 바인딩.

docs/layer-rules.md 1절 / task-01
"""

import logging
import uuid
from collections.abc import Awaitable, Callable

import structlog
from fastapi import Request, Response

from app.core.config import get_settings


def configure_logging() -> None:
    """local 은 콘솔, 그 외는 JSON. 토큰/평문 비밀은 어떤 경우에도 넣지 않는다."""
    settings = get_settings()
    renderer: structlog.typing.Processor = (
        structlog.dev.ConsoleRenderer()
        if settings.app_env == "local"
        else structlog.processors.JSONRenderer()
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        cache_logger_on_first_use=True,
    )


async def request_id_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """요청마다 request_id 를 contextvar 에 바인딩한다."""
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(request_id=request_id, path=request.url.path)
    response = await call_next(request)
    response.headers["x-request-id"] = request_id
    return response
