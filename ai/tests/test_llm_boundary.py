import math
from asyncio import run
from collections.abc import Callable
from dataclasses import FrozenInstanceError

import pytest

from devon_ai import contracts as c


def _prompt() -> c.PromptSpec:
    return c.PromptSpec("repo_shallow", "repo_shallow_v1", "gpt-5.6-luna", "Summarize")


def _limits() -> c.CallLimits:
    return c.CallLimits(10.0, 1024, 4096, 8192)


def _metadata(**changes: object) -> c.AttemptMetadata:
    values: dict[str, object] = {
        "attempt": 1,
        "provider": "openai",
        "model": "gpt-5.6-luna",
        "prompt_version": "repo_shallow_v1",
        "schema_version": "1",
        "latency_ms": 12,
        "input_tokens": None,
        "output_tokens": 8,
        "raw_output": "private response",
    }
    values.update(changes)
    return c.AttemptMetadata(**values)  # type: ignore[arg-type]


def test_call_contracts_are_frozen_and_hide_payload_text_from_repr() -> None:
    prompt = _prompt()
    request = c.ModelRequest(prompt, {"readme": "private input"}, "Repo", "1", {}, _limits())
    result = c.ModelResult(
        data={"summary": "private result"}, failure=None, attempts=(_metadata(),)
    )

    assert "Summarize" not in repr(prompt)
    assert "private input" not in repr(request)
    assert "private response" not in repr(result)
    assert "private result" not in repr(result)
    assert result.succeeded
    with pytest.raises(FrozenInstanceError):
        prompt.version = "changed"


@pytest.mark.parametrize(
    "field,value",
    [
        ("timeout_seconds", 0.0),
        ("timeout_seconds", math.inf),
        ("timeout_seconds", True),
        ("max_output_tokens", 0),
        ("max_output_tokens", 1.5),
        ("max_output_tokens", True),
        ("max_input_bytes", -1),
        ("max_response_bytes", 0),
    ],
)
def test_call_limits_require_positive_finite_numbers(field: str, value: object) -> None:
    values: dict[str, object] = {
        "timeout_seconds": 10.0,
        "max_output_tokens": 1024,
        "max_input_bytes": 4096,
        "max_response_bytes": 8192,
    }
    values[field] = value
    with pytest.raises(c.ContractError) as failure:
        c.CallLimits(**values)  # type: ignore[arg-type]
    assert failure.value.stage == "schema"


def test_model_result_contains_exactly_one_outcome() -> None:
    failure = c.CallFailure("timeout", "llm_timeout", "provider timed out")
    failed = c.ModelResult[dict[str, object]](None, failure, ())
    assert not failed.succeeded

    with pytest.raises(c.ContractError):
        c.ModelResult(None, None, (_metadata(),))
    with pytest.raises(c.ContractError):
        c.ModelResult({}, failure, (_metadata(),))


def test_empty_raw_output_is_preserved_without_appearing_in_repr() -> None:
    metadata = _metadata(raw_output="")
    assert metadata.raw_output == ""
    assert "raw_output" not in repr(metadata)


@pytest.mark.parametrize(
    "changes",
    [
        {"attempt": 0},
        {"attempt": True},
        {"latency_ms": -1},
        {"input_tokens": -1},
        {"input_tokens": True},
        {"output_tokens": -1},
        {"error_stage": "unknown"},
    ],
)
def test_attempt_metadata_rejects_invalid_counters_and_stage(changes: dict[str, object]) -> None:
    with pytest.raises(c.ContractError):
        _metadata(**changes)


def test_model_request_requires_runtime_contract_instances_and_mappings() -> None:
    request = c.ModelRequest(_prompt(), {"repository_id": "repo-1"}, "Repo", "1", {}, _limits())
    assert request.prompt.version == "repo_shallow_v1"

    with pytest.raises(c.ContractError):
        c.ModelRequest(_prompt(), [], "Repo", "1", {}, _limits())  # type: ignore[arg-type]
    with pytest.raises(c.ContractError):
        c.ModelRequest(_prompt(), {}, " ", "1", {}, _limits())


def test_model_call_fake_uses_the_same_request_validator_result_boundary() -> None:
    async def fake_call(
        request: c.ModelRequest, validator: Callable[[object], int]
    ) -> c.ModelResult[int]:
        return c.ModelResult(
            validator({"value": 3}),
            None,
            (_metadata(model=request.prompt.model, prompt_version=request.prompt.version),),
        )

    call: c.ModelCall[int] = fake_call
    request = c.ModelRequest(_prompt(), {}, "Integer", "1", {}, _limits())
    result = run(call(request, lambda raw: raw["value"]))  # type: ignore[index,return-value]

    assert result.data == 3
    assert result.succeeded
