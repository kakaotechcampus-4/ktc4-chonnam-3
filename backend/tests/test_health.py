"""헬스체크 엔드포인트와 request_id 미들웨어 계약.

task-01
"""

from uuid import UUID

import httpx
import pytest

from app.core.config import get_settings
from app.core.logging import REQUEST_ID_HEADER
from app.main import create_app


@pytest.fixture
async def client():
    # 헬스·라우팅 검사는 DB/Redis나 인증 설정 없이 실행되어야 한다.
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app()), base_url="http://test"
    ) as instance:
        yield instance


async def test_health_returns_ok(client: httpx.AsyncClient) -> None:
    prefix = get_settings().api_prefix
    response = await client.get(f"{prefix}/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_health_is_mounted_under_api_prefix(client: httpx.AsyncClient) -> None:
    """prefix 밖 경로는 열지 않는다 — 배포 헬스체크가 /api/health 를 친다."""
    response = await client.get("/health")

    assert response.status_code == 404


async def test_request_id_is_generated_when_absent(client: httpx.AsyncClient) -> None:
    prefix = get_settings().api_prefix
    response = await client.get(f"{prefix}/health")

    assert response.headers.get(REQUEST_ID_HEADER)


async def test_request_id_is_echoed_when_supplied(client: httpx.AsyncClient) -> None:
    prefix = get_settings().api_prefix
    request_id = "550e8400-e29b-41d4-a716-446655440000"
    response = await client.get(f"{prefix}/health", headers={REQUEST_ID_HEADER: request_id})

    assert response.headers[REQUEST_ID_HEADER] == request_id


async def test_non_uuid_request_id_is_replaced(client: httpx.AsyncClient) -> None:
    # 임의 헤더 문자열이 인증 정보 등을 로그 문맥에 실어 보내지 못하게 한다.
    response = await client.get("/api/health", headers={REQUEST_ID_HEADER: "untrusted-value"})
    assert str(UUID(response.headers[REQUEST_ID_HEADER])) != "untrusted-value"
