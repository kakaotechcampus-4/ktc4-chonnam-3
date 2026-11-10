"""질문 복구의 영구 오류와 저장 요청 상태 경계."""

from types import SimpleNamespace
from uuid import uuid4

import pytest


@pytest.mark.parametrize(
    "failure",
    [
        {
            "stage": "provider",
            "error_code": "llm_failed",
            "reason_summary": "Provider HTTP 401 request failed.",
        },
        {
            "stage": "provider",
            "error_code": "llm_failed",
            "reason_summary": "Provider HTTP 403 request failed.",
        },
        {
            "stage": "provider",
            "error_code": "llm_failed",
            "reason_summary": "Provider HTTP 429 request failed.",
        },
    ],
)
def test_permanent_or_unclassified_provider_failure_is_not_retryable(failure):
    from app.features.interview import question_retry

    assert not question_retry.retryable_failure(
        failure, [{"raw_output": '{"error":{"code":"insufficient_quota"}}'}]
    )


def test_candidate_rewrite_and_timeout_remain_retryable():
    from app.features.interview import question_retry

    assert question_retry.retryable_failure(
        {"stage": "semantic", "error_code": "director_candidate_rewrite"}, []
    )
    assert question_retry.retryable_failure({"stage": "timeout", "error_code": "llm_timeout"}, [])


def test_progress_keeps_manual_identity_while_automatic_child_is_running():
    from datetime import UTC, datetime, timedelta
    from uuid import uuid5

    from app.features.interview.question_retry import progress

    request, call = uuid4(), uuid4()
    child = uuid5(call, "automatic-rewrite")
    entry = {
        "request_id": str(request),
        "call_id": str(call),
        "kind": "manual",
        "target": 2,
        "status": "failed",
        "binding": "same",
        "previous_turn_id": "prior",
        "deadline": (datetime.now(UTC) - timedelta(seconds=1)).isoformat(),
    }
    automatic = {
        **entry,
        "request_id": str(child),
        "kind": "auto",
        "status": "running",
        "failed_call_id": str(call),
        "deadline": (datetime.now(UTC) + timedelta(seconds=30)).isoformat(),
    }
    row = SimpleNamespace(
        status="in_progress",
        current_turn=1,
        context_state={"question_retry_v1": {str(request): entry, str(child): automatic}},
    )
    state = progress(row)
    assert state.request_id == request and state.status == "running"
