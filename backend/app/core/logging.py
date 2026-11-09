"""Structured logs without OAuth credentials, callback codes or session cookies."""

import logging
import sys
from collections.abc import MutableMapping
from pathlib import Path
from time import perf_counter
from types import TracebackType
from typing import Any
from uuid import UUID, uuid4

import structlog
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send
from structlog.types import Processor

from app.core.config import LogLevel

REQUEST_ID_HEADER = "X-Request-ID"
_HTTP_METHODS = {"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "TRACE", "CONNECT"}

_SECRET_KEYS = {
    "access_token",
    "refresh_token",
    "client_secret",
    "token_encryption_key",
    "github_client_secret",
    "authorization",
    "cookie",
    "set_cookie",
    "devon_session",
    "oauthstate",
    "state",
    "code",
    "code_verifier",
    "access_token_encrypted",
    "api_key",
    "proxy_token",
    "token",
    "password",
    "database_url",
    "redis_url",
    "base_url",
    "chat_proxy_url",
    "chat_proxy_url_2",
    "chat_proxy_url_3",
    "sql",
    "statement",
    "parameters",
    "params",
    "locals",
    "error",
}


def _secret_key(key: object) -> bool:
    value = str(key).casefold().replace("-", "_")
    return value in _SECRET_KEYS or value.endswith(
        ("_api_key", "_access_token", "_client_secret", "_password")
    )


def redact_secrets(
    _logger: object, _method: str, event: MutableMapping[str, Any]
) -> dict[str, Any]:
    def clean(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: "[REDACTED]" if _secret_key(key) else clean(item)
                for key, item in value.items()
            }
        if isinstance(value, (list, tuple)):
            return [clean(item) for item in value]
        if isinstance(value, BaseException):
            return {"exception_type": type(value).__name__}
        return value

    return {key: "[REDACTED]" if _secret_key(key) else clean(value) for key, value in event.items()}


def _exception_details(raw: object) -> dict[str, object]:
    if raw is True:
        raw = sys.exc_info()
    if isinstance(raw, BaseException):
        raw = (type(raw), raw, raw.__traceback__)
    if not isinstance(raw, tuple) or len(raw) != 3:
        return {}
    exception_type, _, traceback = raw
    if not isinstance(exception_type, type) or not issubclass(exception_type, BaseException):
        return {}
    frames: list[dict[str, object]] = []
    # 소스 문장·절대경로·지역변수·예외 메시지는 읽거나 직렬화하지 않는다.
    while isinstance(traceback, TracebackType):
        code = traceback.tb_frame.f_code
        frames.append(
            {
                "file": Path(code.co_filename).name,
                "function": code.co_name,
                "line": traceback.tb_lineno,
            }
        )
        traceback = traceback.tb_next
    return {"exception_type": exception_type.__name__, "exception_frames": frames[-32:]}


def _safe_exception(
    _logger: object, _method: str, event: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    event.update(_exception_details(event.pop("exc_info", None)))
    for field in ("exception", "exc_text", "stack_info", "stack"):
        event.pop(field, None)
    return event


def _redact_server_exception(record: logging.LogRecord) -> bool:
    details = _exception_details(record.exc_info)
    if not details and isinstance(record.args, tuple):
        for value in record.args:
            if isinstance(value, BaseException):
                details = _exception_details(value)
                break
    if details:
        # ARQ는 예외를 메시지 인자에도 넣으므로 traceback만 지우면 원문이 유출된다.
        record.msg = "Application exception (%s)"
        record.args = (details["exception_type"],)
        record.__dict__.update(details)
    record.exc_info = None
    record.exc_text = None
    record.stack_info = None
    return True


def configure_logging(level: LogLevel = "INFO", *, json_logs: bool = False) -> None:
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level)
    logging.getLogger().setLevel(level)
    for name in ("uvicorn.error", "arq.worker"):
        target = logging.getLogger(name)
        if _redact_server_exception not in target.filters:
            target.addFilter(_redact_server_exception)
    # 외부 API URL, callback 쿼리, SQL 인자에 인증 정보가 포함될 수 있다.
    for name in ("httpx", "httpcore", "uvicorn.access", "sqlalchemy.engine"):
        logging.getLogger(name).setLevel(logging.WARNING)
    common: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
    ]
    renderer = (
        structlog.processors.JSONRenderer()
        if json_logs
        else structlog.dev.ConsoleRenderer(colors=False)
    )
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=[
            *common,
            structlog.stdlib.ExtraAdder(allow={"exception_type", "exception_frames"}),
        ],
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            _safe_exception,
            redact_secrets,
            renderer,
        ],
    )
    loggers = [logging.getLogger()] + [
        item
        for item in logging.Logger.manager.loggerDict.values()
        if isinstance(item, logging.Logger)
    ]
    # 부모 logger의 filter는 자식에 전파되지 않으므로 실제 출력 handler에서도 막는다.
    for handler in {handler for target in loggers for handler in target.handlers}:
        if _redact_server_exception not in handler.filters:
            handler.addFilter(_redact_server_exception)
        handler.setFormatter(formatter)
    structlog.configure(
        processors=[
            *common,
            _safe_exception,
            redact_secrets,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
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
            request_id = str(UUID(Headers(scope=scope).get(REQUEST_ID_HEADER, "")))
        except ValueError:
            request_id = str(uuid4())
        tokens = structlog.contextvars.bind_contextvars(request_id=request_id)
        started = perf_counter()
        status_code = 500

        async def send_with_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            try:
                # router가 확정한 template만 사용하고 원래 path·query·본문은 남기지 않는다.
                template = getattr(scope.get("route"), "path", None)
                route = template if isinstance(template, str) else "unmatched"
                if route != "/api/health":
                    raw_method = scope.get("method")
                    method = (
                        raw_method
                        if isinstance(raw_method, str) and raw_method in _HTTP_METHODS
                        else "OTHER"
                    )
                    get_logger(__name__).info(
                        "http_request",
                        method=method,
                        route=route,
                        status_code=status_code,
                        latency_ms=round(max(0.0, perf_counter() - started) * 1000, 3),
                    )
            except Exception:
                # 관측 출력의 오류가 원래 HTTP 결과나 전파할 예외를 바꾸지 않게 한다.
                pass
            finally:
                structlog.contextvars.reset_contextvars(**tokens)
