"""전역 예외 핸들러 3개(AppError / RequestValidationError / Exception). error 봉투로 통일.

docs/error-reasons.md / task-05
"""

from typing import cast

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.errors import AppError, ErrorReason

logger = structlog.get_logger(__name__)


async def app_error_handler(_: Request, exc: Exception) -> JSONResponse:
    """AppError 를 계약 봉투로 직렬화한다."""
    error = cast(AppError, exc)
    return JSONResponse(status_code=error.status_code, content=error.to_envelope())


async def validation_error_handler(_: Request, exc: Exception) -> JSONResponse:
    """FastAPI 기본 detail 응답이 새지 않도록 봉투로 변환한다."""
    validation = cast(RequestValidationError, exc)
    error = AppError(
        ErrorReason.VALIDATION_FAILED,
        details={"fields": [".".join(str(p) for p in e["loc"]) for e in validation.errors()]},
    )
    return JSONResponse(status_code=error.status_code, content=error.to_envelope())


async def unhandled_error_handler(_: Request, exc: Exception) -> JSONResponse:
    """알 수 없는 예외는 internal_error 로만 노출한다 (스택/원문 비공개)."""
    logger.exception("unhandled_error", error=str(exc))
    error = AppError(ErrorReason.INTERNAL_ERROR)
    return JSONResponse(status_code=error.status_code, content=error.to_envelope())


def register_exception_handlers(app: FastAPI) -> None:
    """app factory 에서 호출한다."""
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)
