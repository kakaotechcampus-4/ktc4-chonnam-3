"""SSE를 끝까지 검증해 하나의 구조화 결과로만 발행하는 전송 경계."""

import json
from dataclasses import replace

import httpx
import pytest
from pydantic import SecretStr

from app.integrations.llm.client import call_model
from tests.integrations.test_llm_client import request, response, validate


def event(data):
    return "data: " + json.dumps(data) + "\n\n"


async def invoke(raw, *, limit=16384):
    requests = []

    def transport(req):
        requests.append(json.loads(req.content))
        return httpx.Response(
            200, content=raw.encode(), headers={"Content-Type": "text/event-stream"}
        )

    item = request()
    item = replace(item, limits=replace(item.limits, stream=True, max_response_bytes=limit))
    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as http:
        result = await call_model(
            item,
            validate,
            api_key=SecretStr("test"),
            base_url="https://api.openai.com/v1",
            http_client=http,
        )
    return result, requests


async def test_completed_event_is_validated_and_records_final_usage():
    raw = (
        ": keepalive\n\n"
        + event({"type": "response.output_text.delta", "delta": "untrusted partial"})
        + event({"type": "response.completed", "response": response()})
        + "data: [DONE]\n\n"
    )
    result, requests = await invoke(raw)
    assert result.data == 7 and requests[0]["stream"] is True
    assert result.attempts[0].input_tokens == 12
    assert result.attempts[0].raw_output == '{"value": 7}'


@pytest.mark.parametrize(
    "raw",
    [
        event({"type": "response.output_text.delta", "delta": '{"value":7}'}),
        "data: not-json\n\n",
        event({"type": "error", "message": "do not publish"}),
        event({"type": "response.completed", "response": response()}) * 2,
        event({"type": "response.failed", "response": response()}),
        event({"type": "response.incomplete", "response": response()}),
        event({"type": "response.completed", "response": response()}).rstrip("\n"),
        event({"type": "response.completed", "response": response()}).removesuffix("\n"),
    ],
)
async def test_unfinished_or_invalid_stream_never_returns_a_partial_candidate(raw):
    result, requests = await invoke(raw)
    assert result.data is None and result.failure.stage == "provider"
    assert len(requests) <= 2


async def test_stream_total_bytes_still_use_gateway_budget():
    result, requests = await invoke(
        event({"type": "response.completed", "response": response()}), limit=20
    )
    assert result.failure.stage == "budget" and len(requests) == 1


async def test_stream_semantic_failure_is_not_retried():
    result, requests = await invoke(
        event({"type": "response.completed", "response": response('{"value":-1}')})
    )
    assert result.failure.stage == "semantic" and len(requests) == 1


async def test_unicode_separators_inside_json_are_not_sse_line_boundaries():
    body = response(metadata={"note": "a\u2028b\u2029c\u0085d"})
    raw = (
        "data: "
        + json.dumps({"type": "response.completed", "response": body}, ensure_ascii=False)
        + "\r\n\r\n"
    )
    result, requests = await invoke(raw)
    assert result.data == 7 and len(requests) == 1
