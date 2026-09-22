from dataclasses import FrozenInstanceError, replace

import pytest

from devon_ai import contracts as c


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
