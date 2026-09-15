from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

from app.core.errors import AppError


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error(request: Request, error: AppError) -> JSONResponse:
        return JSONResponse(error.envelope(), status_code=error.status)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError) -> JSONResponse:
        return JSONResponse(AppError("validation_error", 422).envelope(), status_code=422)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, error: HTTPException) -> JSONResponse:
        return JSONResponse(
            AppError(
                "not_found" if error.status_code == 404 else "request_error", error.status_code
            ).envelope(),
            status_code=error.status_code,
        )

    @app.exception_handler(RedisError)
    @app.exception_handler(SQLAlchemyError)
    async def unavailable(request: Request, error: Exception) -> JSONResponse:
        return JSONResponse(AppError("service_unavailable", 503).envelope(), status_code=503)

    @app.exception_handler(Exception)
    async def unexpected(request: Request, error: Exception) -> JSONResponse:
        return JSONResponse(AppError("internal_error", 500).envelope(), status_code=500)
