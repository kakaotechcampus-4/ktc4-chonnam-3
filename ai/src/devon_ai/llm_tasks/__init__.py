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
    started = perf_counter()
    response = await client(request)
    failure = None
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
    attempt = ModelAttempt(
        task_name=request.task_name,
        requested_model=request.model,
        prompt_version=request.prompt_version,
        schema_version=request.schema_version,
        attempt=1,
        latency_ms=(perf_counter() - started) * 1000,
        response=response,
        failure=failure,
    )
    if failure is not None:
        return ModelFailed(failure, (attempt,))
    return ModelSuccess(checked, (attempt,))
