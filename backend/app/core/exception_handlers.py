"""전역 exception handler. 모든 4xx/5xx 를 공통 error envelope 로 감싼다.

docs/error-reasons.md / task-05

FastAPI 기본 {"detail": ...} 응답이 하나라도 새면 계약 위반이라
StarletteHTTPException 과 처리되지 않은 Exception 까지 여기서 막는다.
"""

from typing import Any

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.errors import AppError
from app.core.logging import get_logger
from app.shared.enums import Reason

logger = get_logger(__name__)

# 라우팅 단계에서 FastAPI 가 직접 내는 HTTPException 의 상태코드 -> reason.
# 여기 없는 4xx 는 invalid_request, 5xx 는 internal_error 로 접는다.
_REASON_BY_STATUS: dict[int, Reason] = {
    401: Reason.UNAUTHENTICATED,
    403: Reason.TOKEN_INVALID,
    404: Reason.NOT_FOUND,
    413: Reason.DOCUMENT_TOO_LARGE,
    415: Reason.UNSUPPORTED_DOCUMENT_TYPE,
}


def _json_error(error: AppError) -> JSONResponse:
    """AppError 를 JSONResponse 로 만든다. 입력: AppError. 출력: JSONResponse."""
    headers = {"Retry-After": str(error.retry_after)} if error.retry_after is not None else None
    return JSONResponse(
        status_code=error.status_code,
        content=error.to_envelope(),
        headers=headers,
    )


async def app_error_handler(request: Request, exc: Exception) -> Response:
    """AppError 를 envelope 로 직렬화한다.

    입력: 요청과 예외. 출력: {"error":{reason,message,details}} JSONResponse.
    """
    if not isinstance(exc, AppError):  # pragma: no cover - 등록상 발생하지 않는다
        return await unhandled_exception_handler(request, exc)
    logger.info(
        "app_error",
        reason=exc.reason.value,
        status_code=exc.status_code,
        path=request.url.path,
    )
    return _json_error(exc)


async def validation_error_handler(request: Request, exc: Exception) -> Response:
    """RequestValidationError 를 계약 envelope 로 바꾼다.

    입력: 요청과 예외. 출력: 400 invalid_request JSONResponse.
    FastAPI 기본값은 422 + {"detail": [...]} 라 그대로 두면 계약을 어긴다.
    """
    if not isinstance(exc, RequestValidationError):  # pragma: no cover
        return await unhandled_exception_handler(request, exc)

    fields: list[dict[str, Any]] = [
        {
            "field": ".".join(str(part) for part in error.get("loc", ())),
            "type": error.get("type", ""),
            "message": error.get("msg", ""),
        }
        for error in exc.errors()
    ]
    logger.info("request_validation_error", path=request.url.path, fields=fields)
    return _json_error(AppError(Reason.INVALID_REQUEST, details={"fields": fields}))


async def http_exception_handler(request: Request, exc: Exception) -> Response:
    """FastAPI·Starlette 가 직접 내는 HTTPException 을 envelope 로 바꾼다.

    입력: 요청과 예외. 출력: 같은 상태코드의 envelope JSONResponse.
    라우팅 404, 405 처럼 우리 코드를 거치지 않는 응답이 여기로 온다.
    """
    if not isinstance(exc, StarletteHTTPException):  # pragma: no cover
        return await unhandled_exception_handler(request, exc)

    status_code = exc.status_code
    if status_code in _REASON_BY_STATUS:
        reason = _REASON_BY_STATUS[status_code]
    elif status_code >= 500:
        reason = Reason.INTERNAL_ERROR
    else:
        reason = Reason.INVALID_REQUEST

    logger.info("http_exception", status_code=status_code, path=request.url.path)
    # 상태코드는 원래 값을 유지한다 — 405 를 400 으로 바꾸지 않는다.
    return _json_error(AppError(reason, status_code=status_code))


async def unhandled_exception_handler(request: Request, exc: Exception) -> Response:
    """처리되지 않은 예외를 500 internal_error 로 바꾼다.

    입력: 요청과 예외. 출력: 500 envelope JSONResponse.
    ⚠ 예외 문구를 응답에 담지 않는다. 원인은 로그에만 남긴다.
    """
    logger.exception(
        "unhandled_exception",
        path=request.url.path,
        exc_type=type(exc).__name__,
    )
    return _json_error(AppError(Reason.INTERNAL_ERROR))


def register_exception_handlers(app: FastAPI) -> None:
    """앱에 전역 핸들러 4개를 등록한다. 입력: FastAPI. 출력: 없음."""
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
