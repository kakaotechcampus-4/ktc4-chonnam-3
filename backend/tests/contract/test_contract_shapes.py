"""계약 테스트 — 응답에 snake_case key 가 새지 않고 error envelope 가 유지되는지."""

import re
import uuid

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.errors import REASON_STATUS, AppError, ErrorReason
from app.core.exception_handlers import register_exception_handlers
from app.features.analysis.schemas import (
    AnalysisRunResponse,
    AnalysisRunResultResponse,
    AnalyzingResponse,
    CreateAnalysisRunResponse,
    RepositoryCard,
    StepState,
)
from app.shared.enums import STEP_ORDER, RepoStatus, RunStatus, StepStatus

SNAKE_KEY = re.compile(r"_[a-z]")


def _assert_camel(payload: object) -> None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            assert not SNAKE_KEY.search(key), f"snake_case key leaked: {key}"
            _assert_camel(value)
    elif isinstance(payload, list):
        for item in payload:
            _assert_camel(item)


def test_run_status_response_is_camel_case() -> None:
    response = AnalysisRunResponse(
        run_id=uuid.uuid4(),
        status=RunStatus.RUNNING,
        progress=57,
        steps=[StepState(key=key, status=StepStatus.PENDING) for key in STEP_ORDER],
        failure_reason=None,
        estimated_seconds=None,
    )
    payload = response.model_dump(by_alias=True, mode="json")
    _assert_camel(payload)
    assert [step["key"] for step in payload["steps"]] == [str(key) for key in STEP_ORDER]
    assert payload["failureReason"] is None


def test_repository_card_defaults_are_ai_free() -> None:
    """AI 결과가 없을 때 카드가 어떤 모습으로 내려가는지 고정한다."""
    card = RepositoryCard(
        repository_id=uuid.uuid4(),
        full_name="kim/project-a",
        name="project-a",
        status=RepoStatus.SUCCEEDED,
    )
    payload = card.model_dump(by_alias=True, mode="json")
    _assert_camel(payload)
    assert payload["recommended"] is False
    assert payload["matchScore"] is None
    assert payload["recommendReason"] is None
    assert payload["matchedRequirementIds"] == []
    assert payload["candidateSource"] == "rule_filter"


def test_result_response_keeps_partial_fields() -> None:
    response = AnalysisRunResultResponse(
        run_id=uuid.uuid4(),
        status=RunStatus.FAILED,
        analyzed_count=8,
        failed_count=2,
    )
    payload = response.model_dump(by_alias=True, mode="json")
    _assert_camel(payload)
    assert payload["analyzedCount"] == 8
    assert payload["failedRepositories"] == []
    assert payload["jdRequirements"] == []


def test_create_and_analyzing_responses() -> None:
    created = CreateAnalysisRunResponse(
        run_id=uuid.uuid4(), status=RunStatus.RUNNING, reused=True
    ).model_dump(by_alias=True, mode="json")
    _assert_camel(created)
    assert created["reused"] is True

    analyzing = AnalyzingResponse(retry_after=3).model_dump(by_alias=True, mode="json")
    assert analyzing == {"status": "analyzing", "retryAfter": 3}


@pytest.mark.parametrize(
    ("reason", "status_code"),
    [
        (ErrorReason.POSTING_URL_REQUIRED, 400),
        (ErrorReason.UNSUPPORTED_SITE, 400),
        (ErrorReason.UNAUTHENTICATED, 401),
        (ErrorReason.RUN_IN_PROGRESS, 409),
        (ErrorReason.NOT_READY, 409),
        (ErrorReason.RUN_EXPIRED, 410),
        (ErrorReason.INTERNAL_ERROR, 500),
    ],
)
async def test_error_envelope(reason: ErrorReason, status_code: int) -> None:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/boom")
    async def boom() -> None:
        raise AppError(reason)

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/boom")

    assert response.status_code == status_code == REASON_STATUS[reason]
    body = response.json()
    assert set(body) == {"error"}
    assert body["error"]["reason"] == str(reason)
    assert body["error"]["message"]
    assert body["error"]["details"] == {}


async def test_unknown_exception_becomes_internal_error() -> None:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("db is on fire")

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/boom")

    assert response.status_code == 500
    assert response.json()["error"]["reason"] == "internal_error"
    assert "fire" not in response.text
