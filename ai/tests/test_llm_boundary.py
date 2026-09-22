import asyncio
import json
from dataclasses import FrozenInstanceError, replace

import pytest

from devon_ai import contracts as c
from devon_ai import llm_tasks


@pytest.fixture
def model_request():
    return c.ModelRequest(
        task_name="director_v1",
        model="fixture-model",
        prompt="fixture prompt",
        prompt_version="fixture-p1",
        schema_json='{"type": "object"}',
        schema_version="fixture-s1",
        input_json='{"context": "private input"}',
        timeout_seconds=1.0,
        max_output_tokens=100,
    )


def test_request_preserves_injected_values_without_exposing_prompt_or_input(model_request):
    assert model_request.model == "fixture-model"
    assert model_request.max_output_tokens == 100
    assert model_request.input_json == '{"context": "private input"}'
    assert "private input" not in repr(model_request)
    assert "fixture prompt" not in repr(model_request)
    with pytest.raises(FrozenInstanceError):
        model_request.model = "different"


@pytest.mark.parametrize("value", [0, -1, float("inf"), float("nan"), True, "1", None])
def test_timeout_must_be_a_finite_positive_number(model_request, value):
    with pytest.raises(ValueError, match="timeout_seconds"):
        replace(model_request, timeout_seconds=value)


@pytest.mark.parametrize("value", [0, -1, 1.5, True, "1", None])
def test_output_budget_must_be_a_positive_integer(model_request, value):
    with pytest.raises(ValueError, match="max_output_tokens"):
        replace(model_request, max_output_tokens=value)


@pytest.mark.parametrize("name", ["model", "task_name", "prompt_version", "schema_version"])
def test_call_identity_must_be_explicit(model_request, name):
    with pytest.raises(ValueError, match=name):
        replace(model_request, **{name: " "})


def test_response_distinguishes_unknown_tokens_from_zero_and_hides_raw_output():
    unknown = c.ModelResponse(raw_output="private output", model="actual-model")
    assert unknown.input_tokens is None and unknown.output_tokens is None
    assert replace(unknown, input_tokens=0, output_tokens=0).input_tokens == 0
    assert unknown.raw_output == "private output"
    assert "private output" not in repr(unknown)


@pytest.mark.parametrize("value", [-1, True, 1.5, "1"])
@pytest.mark.parametrize("name", ["input_tokens", "output_tokens"])
def test_response_rejects_invalid_token_metadata(value, name):
    with pytest.raises(ValueError, match=name):
        c.ModelResponse(raw_output="{}", model="actual-model", **{name: value})


@pytest.fixture
def decision_data():
    return dict(
        next_step="finish",
        intent="종료",
        persona=None,
        target=None,
        tool_requests=[],
        reason_summary="완료된 면접",
    )


def check_decision(candidate):
    return c.validate_decision(
        candidate,
        question=None,
        allowed_personas=(),
        finish_allowed=True,
        allowed_locations=frozenset(),
    )


class FakeClient:
    def __init__(self, *outcomes):
        self.outcomes = iter(outcomes)
        self.requests = []

    async def __call__(self, model_request):
        self.requests.append(model_request)
        outcome = next(self.outcomes)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def invoke(model_request, client, validator=check_decision):
    return asyncio.run(
        asyncio.wait_for(
            llm_tasks.call_model(
                model_request,
                client=client,
                contract_type=c.DirectorDecision,
                validate=validator,
            ),
            timeout=1.0,
        )
    )


def test_success_requires_contract_checks_and_records_actual_metadata(model_request, decision_data):
    response = c.ModelResponse(json.dumps(decision_data), "actual-version", 12, 8)
    client = FakeClient(response)
    result = invoke(model_request, client)
    assert isinstance(result, c.ModelSuccess)
    assert isinstance(result.data, c.ContractChecked)
    assert result.data.data.next_step == "finish"
    assert client.requests == [model_request]
    (attempt,) = result.attempts
    assert attempt.attempt == 1 and attempt.latency_ms >= 0
    assert attempt.requested_model == "fixture-model"
    assert attempt.prompt_version == "fixture-p1" and attempt.schema_version == "fixture-s1"
    assert attempt.response is response and attempt.failure is None
    assert "완료된 면접" not in repr(result)


@pytest.mark.parametrize(
    ("raw", "stage", "code"),
    [
        ("not json", "parse", "llm_parse_failed"),
        ("{}", "schema", "llm_failed"),
        ('{"next_step":"unknown"}', "schema", "llm_failed"),
    ],
)
def test_invalid_output_never_becomes_success(model_request, raw, stage, code):
    response = c.ModelResponse(raw, "actual")
    client = FakeClient(response, response)
    result = invoke(model_request, client)
    assert isinstance(result, c.ModelFailed)
    assert result.failure.stage == stage and result.failure.error_code == code
    assert not hasattr(result, "data")
    assert result.attempts[0].response.raw_output == raw
    assert len(client.requests) == 2


def test_semantic_failure_is_closed_without_exposing_error_values(model_request, decision_data):
    def reject(candidate):
        raise c.ContractError("semantic", "private rejected value")

    result = invoke(
        model_request, FakeClient(c.ModelResponse(json.dumps(decision_data), "actual")), reject
    )
    assert isinstance(result, c.ModelFailed)
    assert result.failure.stage == "semantic"
    assert "private rejected value" not in repr(result)


def test_validator_cannot_return_an_unchecked_candidate(model_request, decision_data):
    result = invoke(
        model_request,
        FakeClient(c.ModelResponse(json.dumps(decision_data), "actual")),
        lambda candidate: candidate,
    )
    assert isinstance(result, c.ModelFailed)
    assert result.failure.stage == "semantic"


@pytest.mark.parametrize("stage", ["timeout", "provider", "parse", "schema"])
@pytest.mark.parametrize("recover", [True, False])
def test_retryable_failures_have_exactly_two_attempts(model_request, decision_data, stage, recover):
    bad = {
        "timeout": TimeoutError("private transport error"),
        "provider": llm_tasks.ModelProviderError("private transport error"),
        "parse": c.ModelResponse("broken", "actual-v1"),
        "schema": c.ModelResponse("{}", "actual-v1"),
    }[stage]
    good = c.ModelResponse(json.dumps(decision_data), "actual-v2", 5, 7)
    client = FakeClient(bad, good if recover else bad)
    result = invoke(model_request, client)
    assert len(client.requests) == 2
    assert client.requests[0] is client.requests[1] is model_request
    assert [a.attempt for a in result.attempts] == [1, 2]
    assert result.attempts[0].failure.stage == stage
    assert all(a.latency_ms >= 0 for a in result.attempts)
    assert "private transport error" not in repr(result)
    if recover:
        assert isinstance(result, c.ModelSuccess)
        assert result.attempts[1].response is good
    else:
        assert isinstance(result, c.ModelFailed)
        assert result.failure.stage == stage
    if stage in ("timeout", "provider"):
        assert result.attempts[0].response is None


def test_semantic_failure_does_not_consume_a_second_response(model_request, decision_data):
    bad = c.ModelResponse(json.dumps(dict(decision_data, persona="tech_lead")), "actual")
    client = FakeClient(bad, c.ModelResponse(json.dumps(decision_data), "actual"))
    result = invoke(model_request, client)
    assert isinstance(result, c.ModelFailed) and result.failure.stage == "semantic"
    assert len(client.requests) == 1


def test_injected_timeout_cancels_each_hanging_attempt(model_request):
    started, cancelled = [], []

    async def hanging_client(value):
        started.append(value)
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.append(True)

    result = invoke(replace(model_request, timeout_seconds=0.01), hanging_client)
    assert isinstance(result, c.ModelFailed)
    assert result.failure.stage == "timeout" and result.failure.error_code == "llm_timeout"
    assert len(started) == len(cancelled) == 2


def test_external_cancellation_is_not_retried(model_request):
    client = FakeClient(asyncio.CancelledError())
    with pytest.raises(asyncio.CancelledError):
        invoke(model_request, client)
    assert len(client.requests) == 1


def test_programming_errors_are_not_misclassified_as_provider_failures(model_request):
    client = FakeClient(TypeError("adapter implementation bug"))
    with pytest.raises(TypeError, match="adapter implementation bug"):
        invoke(model_request, client)
    assert len(client.requests) == 1


@pytest.mark.parametrize(
    "raw",
    [
        '{"next_step":"ask","next_step":"finish","intent":"종료","persona":null,'
        '"target":null,"tool_requests":[],"reason_summary":"done"}',
        '{"extra": NaN}',
        '{"extra": Infinity}',
        '{"extra": -Infinity}',
        "```json\n{}\n```",
        "",
        '{"truncated":',
    ],
)
def test_invalid_json_is_rejected_without_repair(model_request, raw):
    response = c.ModelResponse(raw, "actual")
    client = FakeClient(response, response)
    result = invoke(model_request, client)
    assert isinstance(result, c.ModelFailed) and result.failure.stage == "parse"
    assert len(result.attempts) == len(client.requests) == 2


def test_retry_preserves_failed_raw_output_and_does_not_log_secrets(
    model_request,
    decision_data,
    caplog,
    capsys,
):
    raw = "private failed output credential=synthetic-secret"
    client = FakeClient(
        c.ModelResponse(raw, "actual-v1"), c.ModelResponse(json.dumps(decision_data), "actual-v2")
    )
    result = invoke(model_request, client)
    assert isinstance(result, c.ModelSuccess)
    assert result.attempts[0].response.raw_output == raw
    assert result.attempts[0].response.input_tokens is None
    assert result.attempts[1].response.model == "actual-v2"
    assert raw not in repr(result) and raw not in caplog.text
    assert capsys.readouterr() == ("", "")


def test_nested_retry_layers_are_rejected_before_the_inner_transport(model_request, decision_data):
    inner = FakeClient(c.ModelResponse(json.dumps(decision_data), "actual"))

    async def nested_client(value):
        return await llm_tasks.call_model(
            value,
            client=inner,
            contract_type=c.DirectorDecision,
            validate=check_decision,
        )

    with pytest.raises(ValueError, match="nested"):
        invoke(model_request, nested_client)
    assert inner.requests == []
    # A failed invocation must release the guard for the next independent call.
    assert isinstance(invoke(model_request, inner), c.ModelSuccess)


def test_independent_concurrent_calls_have_separate_attempt_budgets(model_request, decision_data):
    good = c.ModelResponse(json.dumps(decision_data), "actual")
    first, second = FakeClient(good), FakeClient(TimeoutError(), good)

    async def run_both():
        return await asyncio.gather(
            *[
                llm_tasks.call_model(
                    model_request,
                    client=client,
                    contract_type=c.DirectorDecision,
                    validate=check_decision,
                )
                for client in (first, second)
            ]
        )

    results = asyncio.run(run_both())
    assert all(isinstance(result, c.ModelSuccess) for result in results)
    assert [len(result.attempts) for result in results] == [1, 2]


@pytest.mark.parametrize(
    ("raw", "stages"),
    [("[" * 2000 + "]" * 2000, {"parse", "schema"}), ('{"value":' + "9" * 5000 + "}", {"parse"})],
    ids=["deep-nesting", "large-integer"],
)
def test_parser_resource_limits_remain_typed_failures(model_request, raw, stages):
    response = c.ModelResponse(raw, "actual")
    result = invoke(model_request, FakeClient(response, response))
    assert isinstance(result, c.ModelFailed) and result.failure.stage in stages
    assert len(result.attempts) == 2


def test_client_cannot_turn_an_expired_timeout_into_success(model_request, decision_data):
    calls = []

    async def suppressing_client(value):
        calls.append(value)
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            return c.ModelResponse(json.dumps(decision_data), "late-model")

    result = invoke(replace(model_request, timeout_seconds=0.01), suppressing_client)
    assert isinstance(result, c.ModelFailed) and result.failure.stage == "timeout"
    assert len(calls) == 2
