"""HTTP errors and WebSocket handshake failures use the shared error envelope."""

from typing import cast

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.websockets import WebSocket

from app.core.errors import AppError, Reason
from app.core.logging import get_logger

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


async def validation_error_handler(request: Request, _exc: Exception) -> Response:
    # 검증 오류의 입력값에는 callback code나 인증 정보가 있을 수 있어 응답에 담지 않는다.
    return await app_error_handler(request, AppError(Reason.INVALID_REQUEST))


async def http_exception_handler(request: Request, exc: Exception) -> Response:
    if not isinstance(exc, StarletteHTTPException):
        return await unhandled_exception_handler(request, exc)
    reason = {
        401: Reason.UNAUTHENTICATED,
        404: Reason.NOT_FOUND,
    }.get(
        exc.status_code, Reason.INTERNAL_ERROR if exc.status_code >= 500 else Reason.INVALID_REQUEST
    )
    return await app_error_handler(request, AppError(reason, status_code=exc.status_code))


async def unhandled_exception_handler(request: Request, exc: Exception) -> Response:
    # DB·외부 API 예외 원문에는 토큰, 접속 정보, 응답 본문이 섞일 수 있어 타입만 기록한다.
    logger.error("unhandled_exception", path=request.url.path, exception_type=type(exc).__name__)
    return await app_error_handler(request, AppError(Reason.INTERNAL_ERROR))


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
