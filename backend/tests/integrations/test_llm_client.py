from __future__ import annotations

import asyncio
import json
from dataclasses import replace

import httpx
import pytest
from devon_ai import contracts
from pydantic import SecretStr

from app.integrations.llm import client


def request() -> contracts.ModelRequest:
    return contracts.ModelRequest(
        prompt=contracts.PromptSpec(
            task_name="repo_shallow",
            version="repo_shallow_v1",
            model="configured-model",
            template="Return the requested JSON value.",
        ),
        payload={"repository_id": "repo-a"},
        schema_name="number_result",
        schema_version="1",
        output_schema={
            "type": "object",
            "properties": {"value": {"type": "integer"}},
            "required": ["value"],
            "additionalProperties": False,
        },
        limits=contracts.CallLimits(
            timeout_seconds=1.0,
            max_output_tokens=200,
            max_input_bytes=4096,
            max_response_bytes=4096,
        ),
    )


def validate(payload: object) -> int:
    if not isinstance(payload, dict) or type(payload.get("value")) is not int:
        raise contracts.ContractError("schema", "value")
    if payload["value"] < 0:
        raise contracts.ContractError("semantic", "negative value")
    return payload["value"]


def response(text: str = '{"value": 7}', **changes: object) -> dict[str, object]:
    body: dict[str, object] = {
        "id": "resp_fixture",
        "object": "response",
        "status": "completed",
        "model": "actual-model-snapshot",
        "output": [
            {
                "id": "msg_fixture",
                "type": "message",
                "status": "completed",
                "role": "assistant",
                "content": [{"type": "output_text", "text": text, "annotations": []}],
            }
        ],
        "usage": {"input_tokens": 12, "output_tokens": 4, "total_tokens": 16},
    }
    body.update(changes)
    return body


@pytest.mark.asyncio
async def test_validated_result_records_actual_model_and_injects_only_task_input():
    sent = []

    def transport(req):
        sent.append(req)
        return httpx.Response(200, json=response())

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as http:
        result = await client.call_model(
            request(),
            validate,
            api_key=SecretStr("fixture-key"),
            http_client=http,
        )
    assert result.succeeded and result.data == 7 and result.failure is None
    assert len(sent) == 1
    body = json.loads(sent[0].content)
    assert str(sent[0].url) == "https://api.openai.com/v1/responses"
    assert sent[0].headers["Authorization"] == "Bearer fixture-key"
    assert body["model"] == "configured-model"
    assert body["store"] is False
    assert json.loads(body["input"][0]["content"][0]["text"]) == {"repository_id": "repo-a"}
    assert body["instructions"] == request().prompt.template
    assert body["text"]["format"]["schema"] == request().output_schema
    assert body["max_output_tokens"] == 200
    assert "schema_version" not in body and "attempt" not in body
    meta = result.attempts[0]
    assert (meta.provider, meta.model, meta.prompt_version, meta.schema_version) == (
        "openai",
        "actual-model-snapshot",
        "repo_shallow_v1",
        "1",
    )
    assert (meta.attempt, meta.input_tokens, meta.output_tokens) == (1, 12, 4)
    assert meta.raw_output == '{"value": 7}' and meta.response_id == "resp_fixture"
    assert meta.latency_ms >= 0 and meta.error_stage is None
    assert "fixture-key" not in repr(result) and '{"value": 7}' not in repr(result)


@pytest.mark.asyncio
@pytest.mark.parametrize("first_failure", ["timeout", "provider", "parse", "schema"])
async def test_retryable_failure_uses_exactly_one_retry(first_failure):
    calls = 0

    def transport(req):
        nonlocal calls
        calls += 1
        if calls == 1:
            if first_failure == "timeout":
                raise httpx.ReadTimeout("hidden raw error", request=req)
            if first_failure == "provider":
                return httpx.Response(503, text="hidden raw error")
            if first_failure == "parse":
                return httpx.Response(200, json=response("broken-json"))
            return httpx.Response(200, json=response('{"value": "bad"}'))
        return httpx.Response(200, json=response())

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as http:
        result = await client.call_model(
            request(),
            validate,
            api_key=SecretStr("fixture-key"),
            http_client=http,
        )
    assert result.data == 7 and result.succeeded and calls == 2
    assert [entry.attempt for entry in result.attempts] == [1, 2]
    assert result.attempts[0].error_stage == first_failure
    assert result.attempts[1].error_stage is None


@pytest.mark.asyncio
async def test_semantic_failure_is_terminal_and_does_not_become_empty_success(caplog):
    calls = 0

    def transport(req):
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=response('{"value": -1}'))

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as http:
        result = await client.call_model(
            request(),
            validate,
            api_key=SecretStr("fixture-key"),
            http_client=http,
        )
    assert calls == 1 and not result.succeeded and result.data is None
    assert result.failure.stage == "semantic"
    assert result.attempts[0].raw_output == '{"value": -1}'
    assert "fixture-key" not in caplog.text and '{"value": -1}' not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("text", ["broken-json", '{"value": NaN}', '{"value": 1, "value": 2}'])
async def test_bad_json_is_never_repaired_and_exhausts_at_two_calls(text):
    calls = 0

    def transport(req):
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=response(text))

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as http:
        result = await client.call_model(
            request(),
            validate,
            api_key=SecretStr("fixture-key"),
            http_client=http,
        )
    assert calls == 2 and result.failure.stage == "parse" and result.data is None
    assert result.failure.error_code == "llm_parse_failed"
    assert [entry.raw_output for entry in result.attempts] == [text, text]


@pytest.mark.asyncio
async def test_missing_usage_is_unknown_not_zero():
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda req: httpx.Response(200, json=response(usage=None)),
        )
    ) as http:
        result = await client.call_model(
            request(),
            validate,
            api_key=SecretStr("fixture-key"),
            http_client=http,
        )
    assert result.data == 7
    assert result.attempts[0].input_tokens is None and result.attempts[0].output_tokens is None


@pytest.mark.asyncio
async def test_refusal_and_incomplete_response_cannot_pass_as_valid_json():
    for body, expected_stage in [
        (
            response(status="incomplete", incomplete_details={"reason": "max_output_tokens"}),
            "provider",
        ),
        (
            response(
                output=[
                    {
                        "type": "message",
                        "role": "assistant",
                        "status": "completed",
                        "content": [{"type": "refusal", "refusal": "private refusal"}],
                    }
                ]
            ),
            "semantic",
        ),
    ]:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda req, body=body: httpx.Response(200, json=body),
            )
        ) as http:
            result = await client.call_model(
                request(),
                validate,
                api_key=SecretStr("fixture-key"),
                http_client=http,
            )
        assert result.data is None and result.failure.stage == expected_stage
        assert "private refusal" not in repr(result)


@pytest.mark.asyncio
async def test_input_limit_rejects_before_any_provider_request():
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda req: pytest.fail("over-limit input must not leave the process"),
        )
    ) as http:
        req = replace(request(), limits=replace(request().limits, max_input_bytes=10))
        result = await client.call_model(
            req, validate, api_key=SecretStr("fixture-key"), http_client=http
        )
    assert result.failure.stage == "budget" and result.attempts == ()


@pytest.mark.asyncio
async def test_response_size_limit_stops_reading_and_does_not_retry():
    class HugeResponse(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b"x" * 20
            pytest.fail("the response must be closed after its byte limit")

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda req: httpx.Response(200, stream=HugeResponse()),
        )
    ) as http:
        req = replace(request(), limits=replace(request().limits, max_response_bytes=10))
        result = await client.call_model(
            req, validate, api_key=SecretStr("fixture-key"), http_client=http
        )
    assert result.failure.stage == "budget" and len(result.attempts) == 1


@pytest.mark.asyncio
async def test_shared_batch_budget_prevents_retry_multiplication_across_calls():
    calls = 0
    budget = client.CallBudget()

    def transport(req):
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=response())

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as http:
        first = await client.call_model(
            request(),
            validate,
            api_key=SecretStr("fixture-key"),
            http_client=http,
            budget=budget,
        )
        second = await client.call_model(
            request(),
            validate,
            api_key=SecretStr("fixture-key"),
            http_client=http,
            budget=budget,
        )
        third = await client.call_model(
            request(),
            validate,
            api_key=SecretStr("fixture-key"),
            http_client=http,
            budget=budget,
        )
    assert first.data == second.data == 7
    assert third.failure.stage == "budget" and calls == 2
    assert [entry.attempt for entry in second.attempts] == [1, 2]


@pytest.mark.asyncio
async def test_cancellation_is_propagated_without_retry():
    calls = 0

    async def transport(req):
        nonlocal calls
        calls += 1
        raise asyncio.CancelledError

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as http:
        with pytest.raises(asyncio.CancelledError):
            await client.call_model(
                request(), validate, api_key=SecretStr("fixture-key"), http_client=http
            )
    assert calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("model", [None, "", " ", 123])
async def test_invalid_actual_model_is_a_provider_failure(model):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda req: httpx.Response(200, json=response(model=model)),
        )
    ) as http:
        result = await client.call_model(
            request(),
            validate,
            api_key=SecretStr("fixture-key"),
            http_client=http,
        )
    assert result.data is None and result.failure.stage == "provider"
    assert len(result.attempts) == 2


@pytest.mark.asyncio
async def test_wall_timeout_bounds_a_slow_provider_attempt():
    async def transport(req):
        await asyncio.sleep(1)
        pytest.fail("the total attempt timeout must cancel the request")

    req = replace(request(), limits=replace(request().limits, timeout_seconds=0.01))
    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as http:
        result = await client.call_model(
            req,
            validate,
            api_key=SecretStr("fixture-key"),
            http_client=http,
        )
    assert result.failure.stage == "timeout" and result.failure.error_code == "llm_timeout"
    assert len(result.attempts) == 2


@pytest.mark.asyncio
async def test_semantic_failure_remains_terminal_for_the_shared_operation():
    calls = 0

    def transport(req):
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=response('{"value": -1}'))

    budget = client.CallBudget()
    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as http:
        first = await client.call_model(
            request(),
            validate,
            api_key=SecretStr("fixture-key"),
            http_client=http,
            budget=budget,
        )
        second = await client.call_model(
            request(),
            validate,
            api_key=SecretStr("fixture-key"),
            http_client=http,
            budget=budget,
        )
    assert first.failure == second.failure and calls == 1


@pytest.mark.asyncio
async def test_invalid_input_json_is_rejected_without_a_provider_call():
    req = replace(request(), payload={"value": float("nan")})
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda req: pytest.fail("non-finite input must not leave the process"),
        )
    ) as http:
        result = await client.call_model(
            req,
            validate,
            api_key=SecretStr("fixture-key"),
            http_client=http,
        )
    assert result.failure.stage == "schema" and result.attempts == ()


@pytest.mark.asyncio
@pytest.mark.parametrize("envelope", [True, False])
async def test_deep_json_is_a_typed_parse_failure(envelope):
    deeply_nested = "[" * 5000 + "0" + "]" * 5000
    provider_body = deeply_nested if envelope else json.dumps(response(deeply_nested))
    req = replace(request(), limits=replace(request().limits, max_response_bytes=20000))
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda req: httpx.Response(200, content=provider_body),
        )
    ) as http:
        result = await client.call_model(
            req,
            validate,
            api_key=SecretStr("fixture-key"),
            http_client=http,
        )
    assert result.failure.stage == ("provider" if envelope else "parse")
    assert len(result.attempts) == 2
