"""FastAPI 인스턴스, 라우터 등록, 예외 핸들러, lifespan.

docs/layer-rules.md 1절 / task-01
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import get_settings
from app.core.exception_handlers import register_exception_handlers
from app.core.logging import configure_logging, request_id_middleware
from app.features.analysis.router import router as analysis_router
from app.workers.arq_app import create_arq_pool


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """ARQ pool 을 앱 수명과 묶는다."""
    app.state.arq = await create_arq_pool()
    try:
        yield
    finally:
        await app.state.arq.aclose()


def create_app() -> FastAPI:
    """app factory. 테스트는 이 함수를 직접 부른다."""
    configure_logging()
    settings = get_settings()
    app = FastAPI(
        title="DEVON API",
        version="1.0.0-sprint1",
        lifespan=lifespan,
        openapi_url=f"{settings.api_prefix}/openapi.json",
        docs_url=f"{settings.api_prefix}/docs",
    )
    app.middleware("http")(request_id_middleware)
    register_exception_handlers(app)
    app.include_router(analysis_router, prefix=settings.api_prefix)

    @app.get(f"{settings.api_prefix}/health", tags=["ops"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
