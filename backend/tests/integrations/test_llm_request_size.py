"""기본 계약의 Unicode·enum·비스트리밍 요청도 실제 전송 바이트로 제한한다."""

from dataclasses import replace

import httpx
from pydantic import SecretStr

from app.integrations.llm.client import call_model, request_size
from tests.integrations.test_llm_client import request, response, validate


async def test_measured_bytes_equal_the_gateway_wire_and_guard_the_exact_limit():
    item = request()
    item = replace(
        item,
        payload={"원문": ['가나다/인용"경로.src', "emoji-🙂.src"]},
        output_schema={"type": "string", "enum": ['가나다/인용"경로.src', "emoji-🙂.src"]},
        limits=replace(item.limits, max_input_bytes=16384),
    )
    size = request_size(item)
    captured = []

    def transport(incoming):
        captured.append(incoming.content)
        return httpx.Response(200, json=response())

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as http:
        accepted = await call_model(
            replace(item, limits=replace(item.limits, max_input_bytes=size)),
            validate,
            api_key=SecretStr("fixture"),
            base_url="https://fixture.invalid/v1",
            http_client=http,
        )
        rejected = await call_model(
            replace(item, limits=replace(item.limits, max_input_bytes=size - 1)),
            validate,
            api_key=SecretStr("fixture"),
            base_url="https://fixture.invalid/v1",
            http_client=http,
        )
    assert accepted.data == 7 and len(captured) == 1 and len(captured[0]) == size
    assert rejected.data is None and rejected.failure.stage == "budget" and rejected.attempts == ()
