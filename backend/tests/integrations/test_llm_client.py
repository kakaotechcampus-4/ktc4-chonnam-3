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
    assert [entry.attempt for entry in first.attempts] == [1]
    assert [entry.attempt for entry in second.attempts] == [2]
    assert third.attempts == ()


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
    assert second.attempts == ()


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


@pytest.mark.parametrize("container", ["array", "object"])
def test_json_depth_has_an_explicit_inclusive_boundary(container):
    opening, closing = ("[", "]") if container == "array" else ('{"x":', "}")
    client._json(opening * 64 + "0" + closing * 64)
    with pytest.raises(ValueError, match="depth"):
        client._json(opening * 65 + "0" + closing * 65)


def test_json_depth_ignores_brackets_inside_strings():
    assert client._json(json.dumps({"text": "[" * 1000})) == {"text": "[" * 1000}


@pytest.mark.asyncio
@pytest.mark.parametrize("envelope_failure", [True, False])
async def test_decoder_recursion_error_is_always_a_typed_failure(monkeypatch, envelope_failure):
    original = client._json

    def fail_json(value):
        if isinstance(value, bytes) == envelope_failure:
            raise RecursionError("fixture parser limit")
        return original(value)

    monkeypatch.setattr(client, "_json", fail_json)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda req: httpx.Response(200, json=response()))
    ) as http:
        result = await client.call_model(
            request(), validate, api_key=SecretStr("fixture-key"), http_client=http
        )
    assert result.failure.stage == ("provider" if envelope_failure else "parse")
    assert len(result.attempts) == 2


@pytest.mark.asyncio
async def test_large_http_error_keeps_provider_classification_and_closes_stream():
    closed = []

    class ErrorPage(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b"x" * 5000
            pytest.fail("error response must stop at its byte limit")

        async def aclose(self):
            closed.append(True)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda req: httpx.Response(502, stream=ErrorPage()))
    ) as http:
        result = await client.call_model(
            request(), validate, api_key=SecretStr("fixture-key"), http_client=http
        )
    assert result.failure.stage == "provider"
    assert len(result.attempts) == len(closed) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
async def test_permanent_http_errors_are_terminal_for_the_shared_budget(status):
    calls = []
    budget = client.CallBudget()

    def transport(req):
        calls.append(req)
        return httpx.Response(status, text="private provider error")

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as http:
        first = await client.call_model(
            request(), validate, api_key=SecretStr("fixture-key"), http_client=http, budget=budget
        )
        second = await client.call_model(
            request(), validate, api_key=SecretStr("fixture-key"), http_client=http, budget=budget
        )
    assert first.failure.stage == "provider" and first.failure == second.failure
    assert len(first.attempts) == len(calls) == 1 and second.attempts == ()
    assert "private provider error" not in repr(first)


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["code", "type"])
@pytest.mark.parametrize(
    "code",
    [
        "insufficient_quota",
        "credit_balance_exhausted",
        "billing_limit_exceeded",
        "organization_usage_limit_exceeded",
    ],
)
async def test_quota_errors_do_not_retry_or_sleep(monkeypatch, field, code):
    async def forbidden_sleep(delay):
        pytest.fail("quota failure must not sleep")

    monkeypatch.setattr(client.asyncio, "sleep", forbidden_sleep)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda req: httpx.Response(
                429, json={"error": {field: code}}, headers={"Retry-After": "0.5"}
            )
        )
    ) as http:
        result = await client.call_model(
            request(), validate, api_key=SecretStr("fixture-key"), http_client=http
        )
    assert result.failure.stage == "provider" and len(result.attempts) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [429, 503])
@pytest.mark.parametrize("retry_after", ["0.5", "Thu, 01 Jan 1970 00:00:01 GMT"])
async def test_retry_after_is_respected_before_a_single_retry(monkeypatch, status, retry_after):
    events = []
    monkeypatch.setattr(client.time, "time", lambda: 0.5)
    monkeypatch.setattr(client.time, "monotonic", lambda: 100.0)

    async def sleep(delay):
        events.append(("sleep", delay))

    def transport(req):
        events.append(("request", len(events)))
        if len(events) == 1:
            return httpx.Response(
                status,
                json={"error": {"code": "rate_limit_exceeded"}},
                headers={"Retry-After": retry_after},
            )
        return httpx.Response(200, json=response())

    monkeypatch.setattr(client.asyncio, "sleep", sleep)
    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as http:
        result = await client.call_model(
            request(), validate, api_key=SecretStr("fixture-key"), http_client=http
        )
    assert result.succeeded and len(result.attempts) == 2
    assert [event[0] for event in events] == ["request", "sleep", "request"]
    assert 0.5 <= events[1][1] <= request().limits.timeout_seconds


@pytest.mark.asyncio
@pytest.mark.parametrize("retry_after", ["60", "1.01"])
async def test_retry_after_above_wait_limit_is_not_shortened(monkeypatch, retry_after):
    async def forbidden_sleep(delay):
        pytest.fail("do not shorten a server minimum delay")

    monkeypatch.setattr(client.asyncio, "sleep", forbidden_sleep)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda req: httpx.Response(429, headers={"Retry-After": retry_after})
        )
    ) as http:
        result = await client.call_model(
            request(), validate, api_key=SecretStr("fixture-key"), http_client=http
        )
    assert result.failure.stage == "provider" and len(result.attempts) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("retry_after", [None, "invalid", "nan", "inf", "-1"])
async def test_temporary_rate_limit_without_valid_hint_uses_bounded_backoff(
    monkeypatch, retry_after
):
    delays = []

    async def sleep(delay):
        delays.append(delay)

    monkeypatch.setattr(client.asyncio, "sleep", sleep)
    headers = {} if retry_after is None else {"Retry-After": retry_after}
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda req: httpx.Response(429, headers=headers))
    ) as http:
        result = await client.call_model(
            request(), validate, api_key=SecretStr("fixture-key"), http_client=http
        )
    assert result.failure.stage == "provider" and len(result.attempts) == 2
    assert len(delays) == 1 and 0 < delays[0] <= request().limits.timeout_seconds


@pytest.mark.asyncio
async def test_cancellation_during_retry_wait_does_not_start_another_attempt(monkeypatch):
    async def cancel(delay):
        raise asyncio.CancelledError

    monkeypatch.setattr(client.asyncio, "sleep", cancel)
    budget = client.CallBudget()
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda req: httpx.Response(429, headers={"Retry-After": "0.5"})
        )
    ) as http:
        with pytest.raises(asyncio.CancelledError):
            await client.call_model(
                request(),
                validate,
                api_key=SecretStr("fixture-key"),
                http_client=http,
                budget=budget,
            )
    assert budget._used == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_code", [[], {"nested": "value"}, 123, None])
async def test_malformed_error_code_is_a_provider_failure_not_a_programming_error(
    monkeypatch, bad_code
):
    async def sleep(delay):
        pass

    monkeypatch.setattr(client.asyncio, "sleep", sleep)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda req: httpx.Response(429, json={"error": {"code": bad_code}})
        )
    ) as http:
        result = await client.call_model(
            request(), validate, api_key=SecretStr("fixture-key"), http_client=http
        )
    assert result.failure.stage == "provider" and len(result.attempts) == 2


@pytest.mark.asyncio
async def test_no_retry_wait_when_request_attempt_limit_is_one(monkeypatch):
    async def forbidden_sleep(delay):
        pytest.fail("there is no next attempt to wait for")

    monkeypatch.setattr(client.asyncio, "sleep", forbidden_sleep)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda req: httpx.Response(429, headers={"Retry-After": "0.5"})
        )
    ) as http:
        result = await client.call_model(
            replace(request(), max_attempts=1),
            validate,
            api_key=SecretStr("fixture-key"),
            http_client=http,
        )
    assert result.failure.stage == "provider" and len(result.attempts) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(("elapsed", "expected_wait"), [(0.0, 0.5), (0.2, 0.3), (0.6, None)])
async def test_shared_budget_preserves_only_the_remaining_retry_wait(
    monkeypatch, elapsed, expected_wait
):
    clock = [100.0]
    calls, waits = [], []
    monkeypatch.setattr(client.time, "monotonic", lambda: clock[0])

    async def sleep(delay):
        waits.append(delay)
        clock[0] += delay

    def transport(req):
        calls.append(clock[0])
        if len(calls) == 1:
            return httpx.Response(429, headers={"Retry-After": "0.5"})
        return httpx.Response(200, json=response())

    monkeypatch.setattr(client.asyncio, "sleep", sleep)
    budget = client.CallBudget()
    limited = replace(request(), max_attempts=1)
    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as http:
        first = await client.call_model(
            limited, validate, api_key=SecretStr("fixture-key"), http_client=http, budget=budget
        )
        assert first.failure.stage == "provider" and waits == []
        clock[0] += elapsed
        second = await client.call_model(
            limited, validate, api_key=SecretStr("fixture-key"), http_client=http, budget=budget
        )
        third = await client.call_model(
            limited, validate, api_key=SecretStr("fixture-key"), http_client=http, budget=budget
        )
    assert second.succeeded and calls[1] >= 100.5
    assert waits == ([] if expected_wait is None else [pytest.approx(expected_wait)])
    assert [item.attempt for item in first.attempts] == [1]
    assert [item.attempt for item in second.attempts] == [2]
    assert third.failure.stage == "budget" and third.attempts == () and len(calls) == 2


@pytest.mark.asyncio
async def test_cancelled_retry_wait_is_preserved_when_the_budget_is_reused(monkeypatch):
    clock = [100.0]
    calls, waits = [], []
    monkeypatch.setattr(client.time, "monotonic", lambda: clock[0])

    async def sleep(delay):
        waits.append(delay)
        if len(waits) == 1:
            clock[0] += 0.2
            raise asyncio.CancelledError
        clock[0] += delay

    def transport(req):
        calls.append(clock[0])
        if len(calls) == 1:
            return httpx.Response(429, headers={"Retry-After": "0.5"})
        return httpx.Response(200, json=response())

    monkeypatch.setattr(client.asyncio, "sleep", sleep)
    budget = client.CallBudget()
    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as http:
        with pytest.raises(asyncio.CancelledError):
            await client.call_model(
                request(),
                validate,
                api_key=SecretStr("fixture-key"),
                http_client=http,
                budget=budget,
            )
        assert calls == [100.0]
        result = await client.call_model(
            request(), validate, api_key=SecretStr("fixture-key"), http_client=http, budget=budget
        )
    assert result.succeeded and [item.attempt for item in result.attempts] == [2]
    assert waits == [pytest.approx(0.5), pytest.approx(0.3)]
    assert calls == [100.0, pytest.approx(100.5)]


@pytest.mark.asyncio
async def test_shared_retry_wait_above_the_new_request_limit_is_terminal(monkeypatch):
    clock = [100.0]
    calls = []
    monkeypatch.setattr(client.time, "monotonic", lambda: clock[0])

    async def forbidden_sleep(delay):
        pytest.fail("do not shorten a server minimum or exceed the next request's wait limit")

    def transport(req):
        calls.append(req)
        return httpx.Response(429, headers={"Retry-After": "0.5"})

    monkeypatch.setattr(client.asyncio, "sleep", forbidden_sleep)
    budget = client.CallBudget()
    limited = replace(request(), max_attempts=1)
    shorter = replace(limited, limits=replace(limited.limits, timeout_seconds=0.1))
    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as http:
        first = await client.call_model(
            limited, validate, api_key=SecretStr("fixture-key"), http_client=http, budget=budget
        )
        clock[0] += 0.2
        second = await client.call_model(
            shorter, validate, api_key=SecretStr("fixture-key"), http_client=http, budget=budget
        )
        third = await client.call_model(
            limited, validate, api_key=SecretStr("fixture-key"), http_client=http, budget=budget
        )
    assert first.failure.stage == second.failure.stage == "provider"
    assert second.failure == third.failure
    assert second.attempts == third.attempts == () and len(calls) == 1


@pytest.mark.asyncio
async def test_permanent_http_error_is_classified_without_reading_its_body():
    class Unreadable(httpx.AsyncByteStream):
        async def __aiter__(self):
            pytest.fail("a known permanent HTTP rejection needs no body")
            yield b""

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda req: httpx.Response(401, stream=Unreadable()))
    ) as http:
        result = await client.call_model(
            request(), validate, api_key=SecretStr("fixture-key"), http_client=http
        )
    assert result.failure.stage == "provider" and len(result.attempts) == 1
    assert result.attempts[0].raw_output is None


@pytest.mark.asyncio
@pytest.mark.parametrize("retry_after", ["60", "9" * 400])
async def test_server_wait_limit_survives_an_unreadable_429_body(monkeypatch, retry_after):
    calls = []

    async def forbidden_sleep(delay):
        pytest.fail("an excessive server delay is terminal")

    class BrokenBody(httpx.AsyncByteStream):
        async def __aiter__(self):
            raise httpx.ReadError("fixture interrupted error response")
            yield b""

    def transport(req):
        calls.append(req)
        return httpx.Response(429, headers={"Retry-After": retry_after}, stream=BrokenBody())

    monkeypatch.setattr(client.asyncio, "sleep", forbidden_sleep)
    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as http:
        result = await client.call_model(
            request(), validate, api_key=SecretStr("fixture-key"), http_client=http
        )
    assert len(calls) == 1 and result.failure.stage == "provider"


@pytest.mark.asyncio
async def test_valid_retry_after_survives_an_unreadable_429_body(monkeypatch):
    events = []
    monkeypatch.setattr(client.time, "monotonic", lambda: 100.0)

    async def sleep(delay):
        events.append(("sleep", delay))

    class BrokenBody(httpx.AsyncByteStream):
        async def __aiter__(self):
            raise httpx.ReadError("fixture interrupted error response")
            yield b""

    def transport(req):
        events.append(("request", 0))
        return httpx.Response(429, headers={"Retry-After": "0.5"}, stream=BrokenBody())

    monkeypatch.setattr(client.asyncio, "sleep", sleep)
    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as http:
        result = await client.call_model(
            request(), validate, api_key=SecretStr("fixture-key"), http_client=http
        )
    assert result.failure.stage == "provider"
    assert events == [("request", 0), ("sleep", 0.5), ("request", 0)]
