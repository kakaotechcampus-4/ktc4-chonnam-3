"""FastAPI composition; one set of settings owns database, Redis and HTTP resources."""

from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager

import httpx
from arq.connections import ArqRedis
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import Settings, get_settings
from app.core.crypto import TokenCipher
from app.core.exception_handlers import register_exception_handlers
from app.core.logging import RequestIdMiddleware, configure_logging
from app.core.security import SessionCookieMiddleware
from app.features.auth.oauth import GitHubOAuth, OAuthStateStore
from app.features.auth.router import router as auth_router
from app.features.auth.session_store import SessionStore
from app.features.me.router import router as me_router


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        settings.validate_auth()
        configure_logging(settings.log_level, json_logs=settings.is_prod)
        async with AsyncExitStack() as stack:
            engine = create_async_engine(settings.database_url, pool_pre_ping=True)
            stack.push_async_callback(engine.dispose)
            redis = ArqRedis.from_url(settings.redis_url)
            stack.push_async_callback(redis.aclose)
            http = await stack.enter_async_context(
                httpx.AsyncClient(timeout=10.0, follow_redirects=False)
            )
            application.state.session_factory = async_sessionmaker(
                engine, expire_on_commit=False, autoflush=False
            )
            application.state.redis = redis
            application.state.http_client = http
            application.state.cipher = TokenCipher(settings.token_encryption_key.get_secret_value())
            application.state.oauth = GitHubOAuth(settings, http)
            application.state.sessions = SessionStore(redis, settings.session_ttl_seconds)
            application.state.oauth_states = OAuthStateStore(redis)
            yield

    application = FastAPI(
        title="DEVON API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None if settings.is_prod else "/docs",
        redoc_url=None,
        openapi_url=None if settings.is_prod else "/openapi.json",
    )
    application.state.settings = settings
    register_exception_handlers(application)
    application.add_middleware(SessionCookieMiddleware, settings=settings)
    application.add_middleware(RequestIdMiddleware)
    application.include_router(auth_router, prefix=settings.api_prefix)
    application.include_router(me_router, prefix=settings.api_prefix)

    @application.get(f"{settings.api_prefix}/health", tags=["ops"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return application


app = create_app()
