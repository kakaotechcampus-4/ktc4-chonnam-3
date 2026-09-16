from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from redis.asyncio import Redis
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from app.core.config import Settings
from app.core.crypto import TokenCipher
from app.core.exception_handlers import register_exception_handlers
from app.core.logging import configure_auth_logging
from app.core.security import Tokens
from app.db.session import create_database
from app.features.auth.github_tokens import GitHubAPI
from app.features.auth.oauth import GitHubOAuth
from app.features.auth.router import router as auth_router
from app.features.auth.session_store import OAuthStateStore
from app.features.me.router import router as me_router
from app.integrations.github.client import GitHubClient


def create_app(
    settings: Settings | None = None, *, github_transport: httpx.AsyncBaseTransport | None = None
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        cfg = settings or Settings()
        configure_auth_logging()
        engine, sessions = create_database(cfg)
        redis = Redis.from_url(
            cfg.redis_url, decode_responses=True, socket_connect_timeout=3, socket_timeout=3
        )
        async with httpx.AsyncClient(
            timeout=10, transport=github_transport, follow_redirects=False
        ) as client:
            app.state.settings = cfg
            app.state.sessions = sessions
            app.state.tokens = Tokens(cfg)
            app.state.cipher = TokenCipher(cfg)
            app.state.oauth_states = OAuthStateStore(redis)
            app.state.oauth = GitHubOAuth(cfg, client)
            app.state.github = GitHubAPI(
                sessions, app.state.oauth, app.state.cipher, GitHubClient(client)
            )
            try:
                yield
            finally:
                await redis.aclose()
                await engine.dispose()

    app = FastAPI(title="DEVON", lifespan=lifespan)
    register_exception_handlers(app)
    app.include_router(auth_router, prefix="/api")
    app.include_router(me_router, prefix="/api")

    @app.middleware("http")
    async def auth_headers(request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    return app


app = create_app()
