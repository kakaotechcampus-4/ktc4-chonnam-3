"""Structured logs without OAuth credentials, callback codes or session cookies."""

import logging
import sys
from collections.abc import MutableMapping
from typing import Any
from uuid import UUID, uuid4

import structlog
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import LogLevel

_SECRET_KEYS = {
    "access_token",
    "refresh_token",
    "client_secret",
    "token_encryption_key",
    "github_client_secret",
    "authorization",
    "cookie",
    "set-cookie",
    "devon_session",
    "oauthstate",
    "state",
    "code",
    "code_verifier",
    "access_token_encrypted",
}


def redact_secrets(
    _logger: object, _method: str, event: MutableMapping[str, Any]
) -> dict[str, Any]:
    def clean(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: "[REDACTED]" if str(key).lower() in _SECRET_KEYS else clean(item)
                for key, item in value.items()
            }
        if isinstance(value, (list, tuple)):
            return [clean(item) for item in value]
        return value

    return {
        key: "[REDACTED]" if key.lower() in _SECRET_KEYS else clean(value)
        for key, value in event.items()
    }


def _redact_server_exception(record: logging.LogRecord) -> bool:
    # Starlette가 처리한 500도 다시 던지므로 Uvicorn이 예외 원문의 비밀값을 기록하지 않게 한다.
    if record.exc_info:
        exception_type = record.exc_info[0]
        record.msg = "ASGI application failed (%s)"
        record.args = (exception_type.__name__ if exception_type else "Exception",)
        record.exc_info = None
        record.exc_text = None
        record.stack_info = None
    return True


def configure_logging(level: LogLevel = "INFO", *, json_logs: bool = False) -> None:
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level)
    logging.getLogger("uvicorn.error").addFilter(_redact_server_exception)
    # 외부 API URL, callback 쿼리, SQL 인자에 인증 정보가 포함될 수 있다.
    for name in ("httpx", "httpcore", "uvicorn.access", "sqlalchemy.engine"):
        logging.getLogger(name).setLevel(logging.WARNING)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            redact_secrets,
            structlog.processors.JSONRenderer()
            if json_logs
            else structlog.dev.ConsoleRenderer(colors=False),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelNamesMapping()[level]),
        logger_factory=structlog.stdlib.LoggerFactory(),
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(name)
    return logger


class RequestIdMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        try:
            request_id = str(UUID(Headers(scope=scope).get("x-request-id", "")))
        except ValueError:
            request_id = str(uuid4())
        tokens = structlog.contextvars.bind_contextvars(request_id=request_id)

        async def send_with_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)["X-Request-ID"] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            structlog.contextvars.reset_contextvars(**tokens)
