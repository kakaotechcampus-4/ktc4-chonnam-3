"""HTTP errors and WebSocket handshake failures use the shared error envelope."""

from collections.abc import Awaitable, Callable
from typing import cast

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.websockets import WebSocket

from app.core.errors import AppError
from app.core.logging import get_logger
from app.shared.enums import Reason

logger = get_logger(__name__)


async def app_error_handler(request: Request, exc: Exception) -> Response:
    error = exc if isinstance(exc, AppError) else AppError(Reason.INTERNAL_ERROR)
    response = JSONResponse(
        error.to_envelope(),
        status_code=error.status_code,
        headers={"Cache-Control": "no-store"},
    )
    if error.retry_after is not None:
        response.headers["Retry-After"] = str(error.retry_after)
    logger.info("request_failed", path=request.url.path, reason=error.reason.value)
    if request.scope["type"] == "websocket":
        websocket = cast(WebSocket, request)
        if "websocket.http.response" in websocket.scope.get("extensions", {}):
            await websocket.send_denial_response(response)
        else:
            await websocket.close(code=1008, reason=error.reason.value)
    return response


async def validation_error_handler(request: Request, exc: Exception) -> Response:
    if not isinstance(exc, RequestValidationError):
        return await unhandled_exception_handler(request, exc)
    # 필드 위치는 알려주되 input·ctx·원문 메시지에 섞인 인증 정보는 반환·기록하지 않는다.
    fields = [
        {
            "field": ".".join(str(part) for part in error.get("loc", ())),
            "type": error.get("type", ""),
            "message": "입력 형식을 확인해 주세요.",
        }
        for error in exc.errors()
    ]
    return await app_error_handler(
        request, AppError(Reason.INVALID_REQUEST, details={"fields": fields})
    )


async def http_exception_handler(request: Request, exc: Exception) -> Response:
    if not isinstance(exc, StarletteHTTPException):
        return await unhandled_exception_handler(request, exc)
    reason = {
        401: Reason.UNAUTHENTICATED,
        404: Reason.NOT_FOUND,
        413: Reason.DOCUMENT_TOO_LARGE,
        415: Reason.UNSUPPORTED_DOCUMENT_TYPE,
    }.get(
        exc.status_code, Reason.INTERNAL_ERROR if exc.status_code >= 500 else Reason.INVALID_REQUEST
    )
    response = await app_error_handler(request, AppError(reason, status_code=exc.status_code))
    # 405의 Allow 등 원래 HTTP 헤더를 공통 오류 응답으로 바꾸면서 잃지 않는다.
    if exc.headers:
        response.headers.update(exc.headers)
    return response


async def unhandled_exception_handler(request: Request, exc: Exception) -> Response:
    # DB·외부 API 예외 원문에는 토큰, 접속 정보, 응답 본문이 섞일 수 있어 타입만 기록한다.
    logger.error("unhandled_exception", path=request.url.path, exception_type=type(exc).__name__)
    return await app_error_handler(request, AppError(Reason.INTERNAL_ERROR))


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)


async def unhandled_exception_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """500도 request ID·세션 응답 미들웨어를 통과하도록 안쪽에서 변환한다."""
    try:
        return await call_next(request)
    except Exception as exc:
        return await unhandled_exception_handler(request, exc)


def register_unhandled_exception_middleware(app: FastAPI) -> None:
    app.middleware("http")(unhandled_exception_middleware)
