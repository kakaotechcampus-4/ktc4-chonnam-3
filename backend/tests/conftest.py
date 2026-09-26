"""테스트 DB / Redis 픽스처, httpx AsyncClient(ASGITransport). SQLite 로 대체하지 않는다.

docs/testing.md / task-01

task-01 범위에서는 ASGI 클라이언트만 둔다.
DB / Redis 픽스처는 PostgreSQL 이 필요하므로 task-02 에서 추가한다.
"""

from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport

from app.main import create_app


@pytest.fixture
def app() -> FastAPI:
    """테스트용 FastAPI 앱. get_settings() 캐시를 그대로 쓴다."""
    return create_app()


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    """ASGITransport 기반 AsyncClient. 실제 소켓을 열지 않는다.

    lifespan 은 실행하지 않는다 — 기동 훅이 필요한 테스트는 별도로 감싼다.
    """
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as async_client:
        yield async_client
