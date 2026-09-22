"""Shared invocation policy; task-specific generation remains in each task."""

import json
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from time import perf_counter
from typing import Never

from devon_ai.contracts import (
    ContractChecked,
    ContractError,
    ModelAttempt,
    ModelFailed,
    ModelFailure,
    ModelRequest,
    ModelResponse,
    ModelSuccess,
    _Contract,
    decode,
)

type ModelCall = Callable[[ModelRequest], Awaitable[ModelResponse]]
_active_call: ContextVar[bool] = ContextVar("devon_ai_model_call", default=False)


class ModelProviderError(Exception):
    """BE maps provider/transport errors here; exception text is never recorded."""


def _json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for name, value in pairs:
        if name in result:
            raise json.JSONDecodeError("duplicate field", "", 0)
        result[name] = value
    return result


def _invalid_constant(value: str) -> Never:
    raise json.JSONDecodeError("non-JSON constant", "", 0)


async def call_model[T: _Contract](
    request: ModelRequest,
    *,
    client: ModelCall,
    contract_type: type[T],
    validate: Callable[[T], ContractChecked[T]],
) -> ModelSuccess[T] | ModelFailed:
    """Decode and independently validate before exposing a successful candidate.

    The injected callable performs one transport attempt with SDK retries off.
    BE owns input preparation, credentials, prompt lookup and durable records.
    """
    if _active_call.get():
        raise ValueError("nested model retry boundaries are not allowed")
    token = _active_call.set(True)
    try:
        return await _call_model(
            request, client=client, contract_type=contract_type, validate=validate
        )
    finally:
        _active_call.reset(token)


async def _call_model[T: _Contract](
    request: ModelRequest,
    *,
    client: ModelCall,
    contract_type: type[T],
    validate: Callable[[T], ContractChecked[T]],
) -> ModelSuccess[T] | ModelFailed:
    # asyncio initializes platform-specific runtime support; defer it until use.
    import asyncio

    attempts: list[ModelAttempt] = []
    for number in (1, 2):
        started = perf_counter()
        response = None
        failure = None
        checked = None
        try:
            async with asyncio.timeout(request.timeout_seconds):
                response = await client(request)
        except TimeoutError:
            failure = ModelFailure("timeout")
        except ModelProviderError:
            failure = ModelFailure("provider")
        else:
            try:
                payload = json.loads(
                    response.raw_output,
                    object_pairs_hook=_json_object,
                    parse_constant=_invalid_constant,
                )
                candidate = decode(contract_type, payload)
                checked = validate(candidate)
                if not isinstance(checked, ContractChecked) or checked.data is not candidate:
                    raise ContractError("semantic", "validator result")
            except json.JSONDecodeError:
                failure = ModelFailure("parse")
            except ContractError as exc:
                failure = ModelFailure(exc.stage)
        attempts.append(
            ModelAttempt(
                task_name=request.task_name,
                requested_model=request.model,
                prompt_version=request.prompt_version,
                schema_version=request.schema_version,
                attempt=number,
                latency_ms=(perf_counter() - started) * 1000,
                response=response,
                failure=failure,
            )
        )
        if failure is None and checked is not None:
            return ModelSuccess(checked, tuple(attempts))
        if failure is not None and (failure.stage == "semantic" or number == 2):
            return ModelFailed(failure, tuple(attempts))
    raise AssertionError("unreachable attempt state")
