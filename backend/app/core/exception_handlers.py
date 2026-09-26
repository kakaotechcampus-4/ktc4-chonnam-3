"""전역 exception handler. 모든 4xx/5xx 를 공통 error envelope 로 감싼다.

docs/error-reasons.md / task-05

FastAPI 기본 {"detail": ...} 응답이 하나라도 새면 계약 위반이라
StarletteHTTPException 과 처리되지 않은 Exception 까지 여기서 막는다.
"""

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.errors import AppError, Reason
from app.core.logging import get_logger

logger = get_logger(__name__)

# 라우팅 단계에서 FastAPI 가 직접 내는 HTTPException 의 상태코드 -> reason.
# 여기 없는 4xx 는 invalid_request, 5xx 는 internal_error 로 접는다.
# ⚠ 403 은 매핑하지 않는다 — github_token_invalid/account_suspended/account_withdrawn
#   모두 403 이라 상태코드만으로는 구분할 수 없고, 우리 인증 코드는 AppError 를 직접
#   raise 하므로 이 fallback 을 타지 않는다. 다른 라이브러리의 HTTPException(403) 이
#   섞였을 때 잘못된 도메인 reason 을 내보내는 쪽보다 invalid_request 로 접는 쪽이 안전하다.
_REASON_BY_STATUS: dict[int, Reason] = {
    401: Reason.UNAUTHENTICATED,
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
    response = _json_error(AppError(reason, status_code=status_code))
    # 원래 HTTPException 의 헤더(405 의 Allow 등)를 유지한다. envelope 로 새로 만들면서
    # 버리면 HTTP 표준이 요구하는 헤더가 응답에서 빠진다.
    if exc.headers:
        response.headers.update(exc.headers)
    return response


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


async def unhandled_exception_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """처리되지 않은 예외를 사용자 미들웨어 스택 안쪽에서 가로챈다.

    Exception 용 add_exception_handler 는 Starlette 의 ServerErrorMiddleware 가 실행하는데,
    이 레이어는 RequestIdMiddleware 를 포함한 사용자 미들웨어 전부보다 바깥이다. 그래서
    처리되지 않은 예외가 곧장 ServerErrorMiddleware 까지 올라가면 RequestIdMiddleware 가
    응답에 X-Request-ID 를 붙일 기회가 없다. 여기서 먼저 잡아 변환하면 그 응답이
    RequestIdMiddleware 를 정상적으로 통과한다.
    """
    try:
        return await call_next(request)
    except Exception as exc:
        return await unhandled_exception_handler(request, exc)


def register_unhandled_exception_middleware(app: FastAPI) -> None:
    """위 미들웨어를 등록한다. RequestIdMiddleware 보다 먼저(= 더 안쪽에) 호출해야 한다."""
    app.middleware("http")(unhandled_exception_middleware)
