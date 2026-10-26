"""도메인 근거 검증이 실제 gateway의 실패 기록·재시도 경계까지 도달하는지 검사한다."""

import json
from functools import partial
from inspect import signature

import httpx
import pytest
from devon_ai import contracts as c
from devon_ai.llm_tasks.domain_category import classify_domain
from pydantic import SecretStr

from app.integrations.llm.client import call_model

PROMPT = c.PromptSpec("domain_category", "domain_category_v2", "fixture-model", "template")
LIMITS = c.CallLimits(1, 200, 20_000, 20_000)
SOURCE = "차량용 제어기 보안\u200b 시험\n도구 개발"
FIXTURE_BASE_URL = "https://fixture.example/v1"


def _envelope(value: object) -> dict[str, object]:
    return {
        "id": "resp_domain",
        "status": "completed",
        "model": "actual-model-snapshot",
        "usage": {"input_tokens": 12, "output_tokens": 4},
        "output": [
            {
                "id": "msg_domain",
                "type": "message",
                "status": "completed",
                "role": "assistant",
                "content": [{"type": "output_text", "text": json.dumps(value)}],
            }
        ],
    }


async def _classify(*outputs: object):
    sent: list[httpx.Request] = []

    def transport(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200, json=_envelope(outputs[min(len(sent) - 1, len(outputs) - 1)]))

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as http:
        model_call = partial(call_model, api_key=SecretStr("fixture-key"), http_client=http)
        # 미병합 #114의 주소 필수 계약도 같은 실제 gateway 회귀로 검사한다.
        # 제품 코드에 기본 주소나 호환용 호출 계층을 추가하는 것은 아니다.
        has_base_url = "base_url" in signature(call_model).parameters
        if has_base_url:
            model_call = partial(model_call, base_url=FIXTURE_BASE_URL)
        decision = await classify_domain(
            c.DomainPostingInput(None, None, (SOURCE,), (), ()),
            prompt=PROMPT,
            limits=LIMITS,
            model_call=model_call,
        )
    base_url = FIXTURE_BASE_URL if has_base_url else "https://api.openai.com/v1"
    assert all(str(request.url) == base_url + "/responses" for request in sent)
    return decision, sent


@pytest.mark.parametrize("evidence_id", [None, "", "main_tasks:9", "main_tasks:00"])
@pytest.mark.asyncio
async def test_unknown_id_is_semantic_failure_with_raw_attempt_and_no_retry(evidence_id):
    invalid = {"category": "mobility", "evidence_id": evidence_id}
    decision, sent = await _classify(invalid, {"category": "etc", "evidence_id": None})

    assert decision.category == "etc" and decision.evidence is None
    assert decision.failure is not None and decision.failure.stage == "semantic"
    assert len(sent) == len(decision.attempts) == 1
    attempt = decision.attempts[0]
    assert (attempt.error_stage, attempt.error_code) == ("semantic", "llm_failed")
    assert attempt.raw_output is not None and json.loads(attempt.raw_output) == invalid
    assert (attempt.prompt_version, attempt.schema_version) == ("domain_category_v2", "2")
    assert (attempt.model, attempt.response_id) == ("actual-model-snapshot", "resp_domain")
    assert (attempt.input_tokens, attempt.output_tokens) == (12, 4)


@pytest.mark.asyncio
async def test_normal_etc_is_success_and_does_not_record_validation_failure():
    decision, sent = await _classify({"category": "etc", "evidence_id": None})

    assert (decision.category, decision.evidence, decision.failure) == ("etc", None, None)
    assert len(sent) == len(decision.attempts) == 1
    assert decision.attempts[0].error_stage is None
    assert decision.attempts[0].error_code is None


@pytest.mark.asyncio
async def test_selected_id_returns_exact_source_and_request_schema_two():
    decision, sent = await _classify({"category": "mobility", "evidence_id": "main_tasks:0"})

    assert decision.category == "mobility" and decision.failure is None
    assert decision.evidence == SOURCE
    assert len(sent) == 1
    body = json.loads(sent[0].content)
    schema = body["text"]["format"]["schema"]
    assert schema["required"] == ["category", "evidence_id"]
    assert "evidence" not in schema["properties"]
    assert json.loads(body["input"][0]["content"][0]["text"])["main_tasks"] == [
        {"id": "main_tasks:0", "text": SOURCE}
    ]


@pytest.mark.asyncio
async def test_schema_failure_uses_only_remaining_gateway_attempt_and_preserves_both():
    invalid = {"category": "mobility", "evidence_id": 1}
    valid = {"category": "mobility", "evidence_id": "main_tasks:0"}
    decision, sent = await _classify(invalid, valid)

    assert decision.category == "mobility" and decision.failure is None
    assert decision.evidence == SOURCE
    assert len(sent) == len(decision.attempts) == 2
    assert [attempt.attempt for attempt in decision.attempts] == [1, 2]
    assert [attempt.error_stage for attempt in decision.attempts] == ["schema", None]
    assert [json.loads(attempt.raw_output) for attempt in decision.attempts] == [invalid, valid]
