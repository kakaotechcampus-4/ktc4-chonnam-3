"""FastAPI 인스턴스, 라우터 등록, 예외 핸들러, lifespan.

docs/layer-rules.md 1절 / task-01
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI

from app.core.config import Settings, get_settings
from app.core.logging import RequestIdMiddleware, configure_logging, get_logger

logger = get_logger(__name__)

health_router = APIRouter(tags=["ops"])


@health_router.get("/health")
async def health() -> dict[str, str]:
    """헬스체크. 입력 없음. 출력: {"status": "ok"}.

    DB·Redis 에 접속하지 않는다 — 의존 서비스 상태는 각자의 체크로 본다.
    """
    return {"status": "ok"}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """앱 수명 주기. 기동 시 로깅을 설정하고 종료를 로그로 남긴다.

    입력: FastAPI 인스턴스. 출력: 없음 (async context manager).
    """
    settings = get_settings()
    configure_logging(settings.log_level, json_logs=settings.is_prod)
    logger.info("app_started", env=settings.app_env, api_prefix=settings.api_prefix)
    yield
    logger.info("app_stopped")


def create_app(settings: Settings | None = None) -> FastAPI:
    """FastAPI 앱을 만든다.

    입력: settings(테스트에서 주입 가능, 기본은 get_settings()).
    출력: 미들웨어와 라우터가 붙은 FastAPI 인스턴스.
    """
    settings = settings or get_settings()
    app = FastAPI(
        title="DEVON API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None if settings.is_prod else "/docs",
        redoc_url=None,
        openapi_url=None if settings.is_prod else "/openapi.json",
    )

    # CORS 미들웨어는 두지 않는다 — local(vite 프록시)·prod 모두 same-origin 이다.
    # docs/deploy.md 2·5절
    app.add_middleware(RequestIdMiddleware)

    app.include_router(health_router, prefix=settings.api_prefix)
    return app


app = create_app()
