"""에러 envelope 계약.

docs/error-reasons.md / task-05

모든 4xx/5xx 가 {"error": {"reason", "message", "details"}} 로 나가는지,
FastAPI 기본 {"detail": ...} 가 새지 않는지 본다.
"""

from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport
from pydantic import BaseModel

from app.core.errors import (
    ANALYSIS_JOB_ERROR_CODES,
    MESSAGE_BY_REASON,
    REPO_ANALYSIS_ERROR_CODES,
    STATUS_BY_REASON,
    AppError,
)
from app.main import create_app
from app.shared.enums import Reason, to_run_status

# 완료 조건이 요구하는 대표 상태코드별 reason.
REPRESENTATIVE_REASONS = [
    (Reason.INVALID_REPOSITORY, 400),
    (Reason.UNAUTHENTICATED, 401),
    (Reason.GITHUB_TOKEN_INVALID, 403),
    (Reason.RUN_IN_PROGRESS, 409),
    (Reason.DOCUMENT_TOO_LARGE, 413),
    (Reason.UNSUPPORTED_DOCUMENT_TYPE, 415),
    (Reason.INTERNAL_ERROR, 500),
]


class _Body(BaseModel):
    posting_url: str


def _build_error_app() -> FastAPI:
    """에러 경로만 붙인 테스트 앱. 입력 없음. 출력: FastAPI."""
    app = create_app()

    @app.get("/raise/{reason}")
    async def _raise(reason: str) -> None:
        raise AppError(Reason(reason))

    @app.get("/raise-retry")
    async def _raise_retry() -> None:
        raise AppError(Reason.NOT_READY, retry_after=3)

    @app.get("/boom")
    async def _boom() -> None:
        raise RuntimeError("비밀이 새면 안 된다")

    @app.post("/echo")
    async def _echo(body: _Body) -> dict[str, str]:
        return {"postingUrl": body.posting_url}

    return app


@pytest.fixture
def error_app() -> FastAPI:
    return _build_error_app()


@pytest.fixture
async def error_client(error_app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=error_app), base_url="http://test"
    ) as client:
        yield client


def _assert_envelope(payload: object) -> dict[str, object]:
    """envelope 모양을 확인하고 error 객체를 돌려준다."""
    assert isinstance(payload, dict)
    assert set(payload) == {"error"}, f"error 외 최상위 키가 있다: {payload}"
    error = payload["error"]
    assert isinstance(error, dict)
    assert {"reason", "message", "details"} <= set(error)
    assert isinstance(error["reason"], str)
    assert isinstance(error["message"], str) and error["message"]
    return error


@pytest.mark.parametrize(("reason", "expected_status"), REPRESENTATIVE_REASONS)
async def test_app_error_returns_envelope(
    error_client: httpx.AsyncClient, reason: Reason, expected_status: int
) -> None:
    response = await error_client.get(f"/raise/{reason.value}")

    assert response.status_code == expected_status
    error = _assert_envelope(response.json())
    assert error["reason"] == reason.value


async def test_retry_after_is_sent_as_header_and_field(error_client: httpx.AsyncClient) -> None:
    response = await error_client.get("/raise-retry")

    assert response.status_code == 409
    assert response.headers["Retry-After"] == "3"
    assert response.json()["error"]["retryAfter"] == 3


async def test_unknown_route_returns_not_found_envelope(error_client: httpx.AsyncClient) -> None:
    """라우팅 404 도 FastAPI 기본 {"detail": ...} 가 아니라 envelope 여야 한다."""
    response = await error_client.get("/no-such-path")

    assert response.status_code == 404
    error = _assert_envelope(response.json())
    assert error["reason"] == Reason.NOT_FOUND.value


async def test_validation_error_becomes_invalid_request(error_client: httpx.AsyncClient) -> None:
    """FastAPI 기본은 422 + detail 이다. 계약 envelope 400 으로 바뀌어야 한다."""
    response = await error_client.post("/echo", json={})

    assert response.status_code == 400
    error = _assert_envelope(response.json())
    assert error["reason"] == Reason.INVALID_REQUEST.value
    details = error["details"]
    assert isinstance(details, dict)
    assert details["fields"], "어느 필드가 틀렸는지 남아야 한다"


async def test_unhandled_exception_becomes_internal_error(error_app: FastAPI) -> None:
    """알 수 없는 예외는 internal_error 로 나가고 예외 문구가 새지 않는다."""
    transport = ASGITransport(app=error_app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/boom")

    assert response.status_code == 500
    error = _assert_envelope(response.json())
    assert error["reason"] == Reason.INTERNAL_ERROR.value
    assert "비밀이 새면 안 된다" not in response.text
    # ServerErrorMiddleware(사용자 미들웨어보다 바깥)로 곧장 새지 않고
    # RequestIdMiddleware 를 통과했는지 — 안쪽 catch 미들웨어가 없으면 이 헤더가 빠진다.
    assert "X-Request-ID" in response.headers


async def test_method_not_allowed_keeps_allow_header(error_client: httpx.AsyncClient) -> None:
    """405 는 envelope 로 바뀌어도 HTTP 표준이 요구하는 Allow 헤더를 유지해야 한다."""
    response = await error_client.get("/echo")

    assert response.status_code == 405
    error = _assert_envelope(response.json())
    assert error["reason"] == Reason.INVALID_REQUEST.value
    assert "Allow" in response.headers


def test_every_reason_has_status_and_message() -> None:
    assert [r for r in Reason if r not in STATUS_BY_REASON] == []
    assert [r for r in Reason if r not in MESSAGE_BY_REASON] == []


def test_job_error_codes_are_not_api_reasons() -> None:
    """내부 job error_code 와 API reason 은 다른 축이다 (task-05)."""
    api_reasons = {r.value for r in Reason}
    job_only = (ANALYSIS_JOB_ERROR_CODES | REPO_ANALYSIS_ERROR_CODES) - api_reasons

    assert {"no_public_repo", "llm_timeout", "llm_parse_failed", "no_readme"} <= job_only


def test_partial_job_status_maps_to_failed() -> None:
    assert to_run_status("partial") == "failed"
    assert to_run_status("succeeded") == "completed"
    assert to_run_status("queued") == "running"
