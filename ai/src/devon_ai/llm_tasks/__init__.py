"""Shared invocation policy; task-specific generation remains in each task."""

import json
from collections.abc import Awaitable, Callable
from time import perf_counter

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


class ModelProviderError(Exception):
    """BE maps provider/transport errors here; exception text is never recorded."""


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
                payload = json.loads(response.raw_output)
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
