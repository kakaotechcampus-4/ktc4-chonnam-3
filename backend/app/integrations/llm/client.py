"""실행 상한을 적용한 OpenAI Responses 호출을 AI에 함수로 주입한다.

한 논리 작업은 부분 배치 재요청까지 같은 CallBudget을 공유한다. 일시적 공급자·parse·schema
오류는 남은 두 번째 시도를 사용할 수 있지만 영구 오류·의미 오류·예산 소진은 즉시 종료한다.
작업별 출력 schema와 검증기는 AI가 소유한다.
"""

from __future__ import annotations

import asyncio
import json
import random
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from email.utils import parsedate_to_datetime
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

MAX_JSON_DEPTH = 64


@dataclass
class CallBudget:
    """같은 논리 작업의 호출끼리만 공유하며 다른 job에서 재사용하지 않는다."""

    _used: int = field(default=0, init=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)
    _terminal: CallFailure | None = field(default=None, init=False, repr=False)
    _retry_not_before: float = field(default=0.0, init=False, repr=False)


class _CallFailed(Exception):
    def __init__(self, failure: CallFailure, retry_delay: float | None = 0.0) -> None:
        self.failure = failure
        # None은 공급자 오류 중에서도 같은 입력으로 복구할 수 없는 종료를 뜻한다.
        self.retry_delay = retry_delay
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
    """엄격한 JSON과 명시적 container 깊이 상한을 검사한다. 루트 container는 깊이 1이다."""
    value: object = json.loads(text, object_pairs_hook=_object, parse_constant=_constant)
    stack = [(value, 1)]
    while stack:
        node, depth = stack.pop()
        if isinstance(node, (dict, list)):
            if depth > MAX_JSON_DEPTH:
                raise ValueError("JSON depth exceeds limit")
            children = node.values() if isinstance(node, dict) else node
            stack.extend((child, depth + 1) for child in children)
    return value


def _retry_delay(header: str | None, max_wait: float) -> float | None:
    """서버 최소 대기를 줄이지 않는다. 누락·잘못된 값은 유한한 jitter 대기로 대체한다."""
    if header is not None:
        try:
            # 큰 양의 초가 float inf로 넘쳐 잘못된 헤더용 짧은 대기로 바뀌면 안 된다.
            delay = Decimal(header)
        except InvalidOperation:
            try:
                date = parsedate_to_datetime(header)
                if date.tzinfo is None:
                    raise ValueError("Retry-After date requires a timezone")
                delay = Decimal(max(0.0, date.timestamp() - time.time()))
            except (ValueError, TypeError, OverflowError, OSError):
                delay = Decimal("NaN")
        if delay.is_finite() and delay >= 0:
            return float(delay) if delay <= max_wait else None
    # Sprint 1은 재시도가 한 번뿐이다. 반복 backoff 계층이나 추가 설정은 만들지 않는다.
    return random.uniform(0.5, 1.0) * min(1.0, max_wait)


def _quota_exhausted(raw: bytes) -> bool:
    try:
        body = _json(raw)
    except (ValueError, UnicodeError, RecursionError):
        return False
    if not isinstance(body, dict) or not isinstance(body.get("error"), dict):
        return False
    error = body["error"]
    terminal_codes = {
        "insufficient_quota",
        "credit_balance_exhausted",
        "billing_limit_exceeded",
        "organization_usage_limit_exceeded",
    }
    return any(
        isinstance(value := error.get(field), str) and value in terminal_codes
        for field in ("code", "type")
    )


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
) -> tuple[T | None, CallFailure | None, AttemptMetadata, float | None]:
    started = time.monotonic()
    model = request.prompt.model
    response_id: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    raw: str | None = None
    failure: CallFailure | None = None
    data: T | None = None
    retry_delay: float | None = 0.0
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
                # 상태를 먼저 구분해 큰 오류 페이지가 실행 budget 오류로 바뀌지 않게 한다.
                if not response.is_success:
                    retry_delay = 0.0
                    status = response.status_code
                    if status == 429:
                        # 오류 본문이 끊기더라도 이미 받은 서버 최소 대기는 보존한다.
                        retry_delay = _retry_delay(
                            response.headers.get("Retry-After"), request.limits.timeout_seconds
                        )
                        if retry_delay is not None:
                            error_body = bytearray()
                            async for chunk in response.aiter_bytes():
                                remaining = request.limits.max_response_bytes - len(error_body)
                                error_body.extend(chunk[:remaining])
                                if len(error_body) >= request.limits.max_response_bytes:
                                    break
                            raw = bytes(error_body).decode("utf-8", errors="replace")
                            if _quota_exhausted(bytes(error_body)):
                                retry_delay = None
                    elif status not in (408, 409) and not 500 <= status < 600:
                        retry_delay = None
                    elif "Retry-After" in response.headers:
                        retry_delay = _retry_delay(
                            response.headers["Retry-After"], request.limits.timeout_seconds
                        )
                    raise _CallFailed(
                        CallFailure(
                            "provider", "llm_failed", f"Provider HTTP {status} request failed."
                        ),
                        retry_delay,
                    )
                buffer = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(buffer) + len(chunk) > request.limits.max_response_bytes:
                        raise _failed(
                            "budget", "llm_failed", "Provider response exceeds byte limit."
                        )
                    buffer.extend(chunk)
                raw = bytes(buffer).decode("utf-8", errors="replace")
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
        retry_delay = exc.retry_delay
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
    return data, failure, metadata, retry_delay


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
    attempts는 이번 함수 호출분만 반환하고, attempt 번호는 공유 budget 안에서 이어진다.
    재시도 대기도 timeout_seconds 이내다. 각 시도 timeout과 별개이며 전체 deadline은 아니다.
    서버 대기는 budget에 보존하며 재호출·취소 이후에도 다음 시도 전에 남은 시간을 기다린다.
    취소와 프로그래밍 오류는 모델 실패로 바꾸지 않고 호출자에게 전파한다.
    """
    budget = budget if budget is not None else CallBudget()
    failure: CallFailure | None
    attempts: list[AttemptMetadata] = []
    async with budget._lock:
        if budget._terminal is not None:
            return ModelResult(data=None, failure=budget._terminal, attempts=())
        try:
            body = _body(request)
        except (TypeError, ValueError, UnicodeError, RecursionError):
            failure = CallFailure(
                stage="schema", error_code="llm_failed", reason_summary="Request is not valid JSON."
            )
            budget._terminal = failure
            return ModelResult(data=None, failure=failure, attempts=())
        if len(body) > request.limits.max_input_bytes:
            failure = CallFailure(
                stage="budget",
                error_code="llm_failed",
                reason_summary="Request exceeds byte limit.",
            )
            budget._terminal = failure
            return ModelResult(data=None, failure=failure, attempts=())
        if budget._used >= 2:
            failure = CallFailure(
                stage="budget",
                error_code="llm_failed",
                reason_summary="Provider call budget exhausted.",
            )
            return ModelResult(data=None, failure=failure, attempts=())
        owns_client = http_client is None
        http = http_client if http_client is not None else httpx.AsyncClient()
        try:
            # 요청별 상한은 이번 호출만 제한하고, 공유 budget의 총 2회 상한은 유지한다.
            remaining_attempts = request.max_attempts
            while budget._used < 2 and remaining_attempts > 0:
                wait = budget._retry_not_before - time.monotonic()
                if wait > request.limits.timeout_seconds:
                    failure = CallFailure(
                        "provider", "llm_failed", "Provider retry delay exceeds wait limit."
                    )
                    budget._terminal = failure
                    break
                if wait > 0:
                    await asyncio.sleep(wait)
                # 취소되면 위 await에서 전파하므로 기존 대기 시점과 남은 시도 수는 보존된다.
                budget._retry_not_before = 0.0
                remaining_attempts -= 1
                budget._used += 1
                data, failure, metadata, retry_delay = await _attempt(
                    request,
                    validator,
                    http,
                    api_key,
                    body,
                    budget._used,
                )
                attempts.append(metadata)
                if failure is None:
                    return ModelResult(data=data, failure=None, attempts=tuple(attempts))
                if failure.stage in {"semantic", "budget"} or retry_delay is None:
                    budget._terminal = failure
                    break
                budget._retry_not_before = time.monotonic() + retry_delay
            return ModelResult(data=None, failure=failure, attempts=tuple(attempts))
        finally:
            if owns_client:
                await http.aclose()
