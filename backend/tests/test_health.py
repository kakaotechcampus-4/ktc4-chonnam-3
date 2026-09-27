"""헬스체크 엔드포인트와 request_id 미들웨어 계약.

task-01
"""

import httpx

from app.core.config import get_settings
from app.core.logging import REQUEST_ID_HEADER


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
    response = await client.get(f"{prefix}/health", headers={REQUEST_ID_HEADER: "caller-supplied"})

    assert response.headers[REQUEST_ID_HEADER] == "caller-supplied"
