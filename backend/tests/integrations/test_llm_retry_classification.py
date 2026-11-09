"""공급자 판정은 보호된 기록의 구조 필드로 전달하며 설명 문구와 분리한다."""

from dataclasses import asdict, replace

import httpx
import pytest
from pydantic import SecretStr

from app.features.interview.question_retry import retryable_failure
from app.integrations.llm.client import call_model
from tests.integrations.test_llm_client import request, validate


@pytest.mark.parametrize(
    "status,body,allowed,cause",
    [
        (401, {}, False, "permanent_http"),
        (403, {}, False, "permanent_http"),
        (503, {}, True, "transient_http"),
        (429, {"error": {"code": "rate_limit_exceeded"}}, True, "rate_limit"),
        (429, {"error": {"type": "insufficient_quota"}}, False, "quota_exhausted"),
        (429, {}, False, "unclassified_http"),
    ],
)
async def test_canonical_failure_is_retryable_after_persistence_without_human_message_matching(
    status, body, allowed, cause
):
    calls = []

    def provider(req):
        calls.append(req)
        return httpx.Response(status, json=body, headers={"Retry-After": "0"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as http:
        result = await call_model(
            replace(request(), max_attempts=1),
            validate,
            api_key=SecretStr("fixture"),
            base_url="https://provider.invalid/v1",
            http_client=http,
        )
    failure = asdict(result.failure)
    assert failure["provider_status"] == status
    assert failure["provider_cause"] == cause and failure["manual_retryable"] is allowed
    failure["reason_summary"] = "공급자 설명 문구를 변경했습니다."
    assert retryable_failure(failure, []) is allowed
    assert len(calls) == 1
