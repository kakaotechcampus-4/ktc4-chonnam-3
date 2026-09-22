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
        llm_tasks.call_model(
            model_request,
            client=client,
            contract_type=c.DirectorDecision,
            validate=validator,
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
    result = invoke(model_request, FakeClient(c.ModelResponse(raw, "actual")))
    assert isinstance(result, c.ModelFailed)
    assert result.failure.stage == stage and result.failure.error_code == code
    assert not hasattr(result, "data")
    assert result.attempts[0].response.raw_output == raw


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
