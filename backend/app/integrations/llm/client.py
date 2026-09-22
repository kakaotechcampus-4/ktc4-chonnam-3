"""실행 상한을 적용한 OpenAI Responses 호출을 AI에 함수로 주입한다.

한 논리 작업은 부분 배치 재요청까지 같은 CallBudget을 공유한다. 공급자·parse·schema
오류는 남은 두 번째 시도를 사용할 수 있지만 의미 오류와 예산 소진은 즉시 종료한다.
작업별 출력 schema와 검증기는 AI가 소유한다.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import cast

import httpx
from devon_ai.contracts import (
    AttemptMetadata,
    CallFailure,
    CallFailureStage,
    ContractError,
    ModelRequest,
    ModelResult,
)
from pydantic import SecretStr


@dataclass
class CallBudget:
    """같은 논리 작업의 호출끼리만 공유하며 다른 job에서 재사용하지 않는다."""

    _used: int = field(default=0, init=False)
    _attempts: list[AttemptMetadata] = field(default_factory=list, init=False, repr=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)
    _terminal: CallFailure | None = field(default=None, init=False, repr=False)


class _CallFailed(Exception):
    def __init__(self, failure: CallFailure) -> None:
        self.failure = failure
        super().__init__(failure.error_code)


def _failed(stage: CallFailureStage, code: str, reason: str) -> _CallFailed:
    return _CallFailed(CallFailure(stage=stage, error_code=code, reason_summary=reason))


def _object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON key")
        value[key] = item
    return value


def _constant(value: str) -> object:
    raise ValueError("non-finite JSON constant")


def _json(text: str | bytes) -> object:
    """중복 key와 NaN/Infinity를 복구하거나 정상 JSON으로 받아들이지 않는다."""
    return json.loads(text, object_pairs_hook=_object, parse_constant=_constant)


def _body(request: ModelRequest) -> bytes:
    body = {
        "model": request.prompt.model,
        "instructions": request.prompt.template,
        "input": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": json.dumps(request.payload, ensure_ascii=False, allow_nan=False),
                    }
                ],
            }
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": request.schema_name,
                "schema": request.output_schema,
                "strict": True,
            }
        },
        "max_output_tokens": request.limits.max_output_tokens,
        "store": False,
    }
    return json.dumps(body, ensure_ascii=False, allow_nan=False).encode("utf-8")


def _token(usage: object, name: str) -> int | None:
    """사용량을 알 수 없으면 0회 사용으로 기록하지 않고 None을 유지한다."""
    if isinstance(usage, dict):
        value = usage.get(name)
        if type(value) is int and value >= 0:
            return value
    return None


def _output(envelope: dict[str, object]) -> tuple[str, bool]:
    output = envelope.get("output")
    if not isinstance(output, list):
        raise _failed("provider", "llm_failed", "Provider output is missing.")
    chunks: list[str] = []
    refusal = False
    for item in output:
        if not isinstance(item, dict):
            raise _failed("provider", "llm_failed", "Invalid provider output.")
        if item.get("type") == "reasoning":
            continue
        if item.get("type") != "message" or item.get("role") != "assistant":
            raise _failed("provider", "llm_failed", "Unexpected provider output type.")
        if item.get("status") != "completed" or not isinstance(item.get("content"), list):
            raise _failed("provider", "llm_failed", "Provider message is incomplete.")
        for content in item["content"]:
            if not isinstance(content, dict):
                raise _failed("provider", "llm_failed", "Invalid provider content.")
            if content.get("type") == "refusal" and isinstance(content.get("refusal"), str):
                refusal = True
                chunks.append(content["refusal"])
            elif content.get("type") == "output_text" and isinstance(content.get("text"), str):
                chunks.append(content["text"])
            else:
                raise _failed("provider", "llm_failed", "Unexpected provider content type.")
    if not chunks:
        raise _failed("provider", "llm_failed", "Provider returned no text.")
    return "".join(chunks), refusal


async def _attempt[T](
    request: ModelRequest,
    validator: Callable[[object], T],
    http: httpx.AsyncClient,
    api_key: SecretStr,
    body: bytes,
    attempt: int,
) -> tuple[T | None, CallFailure | None, AttemptMetadata]:
    started = time.monotonic()
    model = request.prompt.model
    response_id: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    raw: str | None = None
    failure: CallFailure | None = None
    data: T | None = None
    try:
        async with asyncio.timeout(request.limits.timeout_seconds):
            async with http.stream(
                "POST",
                "https://api.openai.com/v1/responses",
                content=body,
                headers={
                    "Authorization": f"Bearer {api_key.get_secret_value()}",
                    "Content-Type": "application/json",
                },
                timeout=request.limits.timeout_seconds,
                follow_redirects=False,
            ) as response:
                buffer = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(buffer) + len(chunk) > request.limits.max_response_bytes:
                        raise _failed(
                            "budget", "llm_failed", "Provider response exceeds byte limit."
                        )
                    buffer.extend(chunk)
                raw = bytes(buffer).decode("utf-8", errors="replace")
                if not response.is_success:
                    raise _failed("provider", "llm_failed", "Provider HTTP request failed.")
        # 공급자 응답 봉투의 손상과 그 안에 담긴 모델 출력의 JSON 오류를 구분한다.
        try:
            decoded = _json(bytes(buffer))
        except (ValueError, UnicodeError, RecursionError):
            raise _failed("provider", "llm_failed", "Invalid provider response JSON.") from None
        if not isinstance(decoded, dict):
            raise _failed("provider", "llm_failed", "Invalid provider response envelope.")
        envelope = cast(dict[str, object], decoded)
        input_tokens = _token(envelope.get("usage"), "input_tokens")
        output_tokens = _token(envelope.get("usage"), "output_tokens")
        actual_model = envelope.get("model")
        if not isinstance(actual_model, str) or not actual_model.strip():
            raise _failed("provider", "llm_failed", "Provider model metadata is missing.")
        model = actual_model
        provider_id = envelope.get("id")
        if not isinstance(provider_id, str) or not provider_id.strip():
            raise _failed("provider", "llm_failed", "Provider response identifier is missing.")
        response_id = provider_id
        if envelope.get("status") != "completed":
            raise _failed("provider", "llm_failed", "Provider response did not complete.")
        raw, refusal = _output(envelope)
        if refusal:
            raise _failed("semantic", "llm_failed", "Provider refused this request.")
        # 봉투 검증을 통과한 뒤에만 작업별 출력의 parse/schema/semantic을 검사한다.
        try:
            parsed = _json(raw)
        except (ValueError, UnicodeError, RecursionError):
            raise _failed("parse", "llm_parse_failed", "Model output is not strict JSON.") from None
        try:
            data = validator(parsed)
        except ContractError as exc:
            code = "llm_parse_failed" if exc.stage == "parse" else "llm_failed"
            raise _failed(exc.stage, code, "Model output failed contract validation.") from None
        if data is None:
            raise _failed("schema", "llm_failed", "Validator returned no result.")
    except (TimeoutError, httpx.TimeoutException):
        failure = CallFailure(
            stage="timeout", error_code="llm_timeout", reason_summary="Provider request timed out."
        )
    except httpx.RequestError:
        failure = CallFailure(
            stage="provider", error_code="llm_failed", reason_summary="Provider transport failed."
        )
    except _CallFailed as exc:
        failure = exc.failure
    # 원문은 보호된 호출 기록에만 담는다. repr에서 숨기며 일반 로그에는 출력하지 않는다.
    metadata = AttemptMetadata(
        attempt=attempt,
        provider="openai",
        model=model,
        prompt_version=request.prompt.version,
        schema_version=request.schema_version,
        latency_ms=max(0, int((time.monotonic() - started) * 1000)),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        error_stage=failure.stage if failure else None,
        error_code=failure.error_code if failure else None,
        raw_output=raw,
        response_id=response_id,
    )
    return data, failure, metadata


async def call_model[T](
    request: ModelRequest,
    validator: Callable[[object], T],
    *,
    api_key: SecretStr,
    http_client: httpx.AsyncClient | None = None,
    budget: CallBudget | None = None,
) -> ModelResult[T]:
    """모델 출력을 검증하고 원문을 로그에 출력하지 않은 채 호출 기록을 반환한다.

    주입한 HTTP client의 수명은 호출자가 관리한다. 기본 client에는 별도 전송 재시도가
    없으며, 부분 배치의 실패 항목을 재요청할 때도 같은 budget을 공유해야 한다.
    취소와 프로그래밍 오류는 모델 실패로 바꾸지 않고 호출자에게 전파한다.
    """
    budget = budget if budget is not None else CallBudget()
    failure: CallFailure | None
    async with budget._lock:
        if budget._terminal is not None:
            return ModelResult(
                data=None, failure=budget._terminal, attempts=tuple(budget._attempts)
            )
        try:
            body = _body(request)
        except (TypeError, ValueError, UnicodeError, RecursionError):
            failure = CallFailure(
                stage="schema", error_code="llm_failed", reason_summary="Request is not valid JSON."
            )
            budget._terminal = failure
            return ModelResult(data=None, failure=failure, attempts=tuple(budget._attempts))
        if len(body) > request.limits.max_input_bytes:
            failure = CallFailure(
                stage="budget",
                error_code="llm_failed",
                reason_summary="Request exceeds byte limit.",
            )
            budget._terminal = failure
            return ModelResult(data=None, failure=failure, attempts=tuple(budget._attempts))
        if budget._used >= 2:
            failure = CallFailure(
                stage="budget",
                error_code="llm_failed",
                reason_summary="Provider call budget exhausted.",
            )
            return ModelResult(data=None, failure=failure, attempts=tuple(budget._attempts))
        owns_client = http_client is None
        http = http_client if http_client is not None else httpx.AsyncClient()
        try:
            # 요청별 상한은 이번 호출만 제한하고, 공유 budget의 총 2회 상한은 유지한다.
            remaining_attempts = request.max_attempts
            while budget._used < 2 and remaining_attempts > 0:
                remaining_attempts -= 1
                budget._used += 1
                data, failure, metadata = await _attempt(
                    request,
                    validator,
                    http,
                    api_key,
                    body,
                    budget._used,
                )
                budget._attempts.append(metadata)
                if failure is None:
                    return ModelResult(data=data, failure=None, attempts=tuple(budget._attempts))
                if failure.stage in {"semantic", "budget"}:
                    budget._terminal = failure
                    break
            return ModelResult(data=None, failure=failure, attempts=tuple(budget._attempts))
        finally:
            if owns_client:
                await http.aclose()
