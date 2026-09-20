"""structlog 설정, request_id 바인딩.

docs/layer-rules.md 1절 / task-01
"""

import logging
import sys
import uuid
from collections.abc import Awaitable, Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from structlog.types import Processor

from app.core.config import LogLevel

REQUEST_ID_HEADER = "X-Request-ID"


def configure_logging(level: LogLevel = "INFO", *, json_logs: bool = False) -> None:
    """structlog 과 표준 logging 을 한 번에 설정한다.

    입력: level(로그 레벨), json_logs(True 면 JSON 한 줄 출력, False 면 사람이 읽는 콘솔).
    출력: 없음. 프로세스 전역 설정을 바꾼다.
    """
    shared: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    renderer: Processor = (
        structlog.processors.JSONRenderer()
        if json_logs
        else structlog.dev.ConsoleRenderer(colors=False)
    )

    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level, force=True)
    structlog.configure(
        processors=[*shared, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelNamesMapping()[level]),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """모듈용 로거를 돌려준다. 입력: 로거 이름. 출력: BoundLogger."""
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(name)
    return logger


def bind_request_id(request_id: str) -> None:
    """이후 같은 컨텍스트의 모든 로그에 request_id 를 붙인다.

    입력: request_id 문자열. 출력: 없음 (contextvars 에 바인딩).
    """
    structlog.contextvars.bind_contextvars(request_id=request_id)


class RequestIdMiddleware(BaseHTTPMiddleware):
    """요청마다 request_id 를 만들어 로그 컨텍스트와 응답 헤더에 싣는다.

    클라이언트가 X-Request-ID 를 보내면 그 값을 이어 쓰고, 없으면 uuid4 를 만든다.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())
        structlog.contextvars.clear_contextvars()
        bind_request_id(request_id)
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response
