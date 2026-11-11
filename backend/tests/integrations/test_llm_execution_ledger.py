"""실제 gateway의 압축 응답·재시도·취소가 장부에 빠짐없이 남는지 확인한다."""

import asyncio
import gzip
import json

import httpx
import pytest
from pydantic import SecretStr

from app.integrations.execution_ledger import ExecutionLedger, execution_scope, summarize
from app.integrations.llm import client
from tests.integrations.test_llm_client import request, response, validate


async def test_gateway_records_compressed_usage_after_decoding_and_preserves_failed_retry(
    tmp_path, monkeypatch
):
    ledger = ExecutionLedger(tmp_path / "calls.sqlite")
    sent = []
    envelope = response(
        usage={
            "input_tokens": 100,
            "output_tokens": 20,
            "input_tokens_details": {"cached_tokens": 40},
            "output_tokens_details": {"reasoning_tokens": 15},
        }
    )

    def handle(req):
        sent.append(req)
        if len(sent) == 1:
            return httpx.Response(503)
        return httpx.Response(
            200,
            headers={"Content-Encoding": "gzip"},
            content=gzip.compress(json.dumps(envelope).encode()),
        )

    monkeypatch.setattr(client, "_retry_delay", lambda *_: 0)
    with execution_scope(ledger, run_id="r", entrypoint="evaluation_cli", provider="elice_mlapi"):
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
            result = await client.call_model(
                request(),
                validate,
                api_key=SecretStr("never-export-this-key"),
                base_url="https://provider.fixture/v1",
                http_client=http,
            )
    assert result.data == 7
    records = ledger.records()
    assert len(records) == len(sent) == 2
    assert [r.status for r in records] == ["failed", "succeeded"]
    assert records[0].input_tokens is None
    assert records[1].input_tokens == 100
    assert records[1].cached_input_tokens == 40
    assert records[1].reasoning_tokens == 15
    assert records[1].requested_model == "configured-model"
    assert records[1].actual_model == "actual-model-snapshot"
    assert summarize(records)["unknown_usage_calls"] == 1
    assert b"never-export-this-key" not in ledger.path.read_bytes()


async def test_cancelled_http_attempt_is_preserved_without_swallowing_cancellation(tmp_path):
    ledger = ExecutionLedger(tmp_path / "calls.sqlite")
    entered = asyncio.Event()

    async def handle(req):
        entered.set()
        await asyncio.Future()

    with execution_scope(ledger, run_id="r", entrypoint="service"):
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
            task = asyncio.create_task(
                client.call_model(
                    request(),
                    validate,
                    api_key=SecretStr("fixture"),
                    base_url="https://provider.fixture/v1",
                    http_client=http,
                )
            )
            await entered.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
    assert len(ledger.records()) == 1
    assert ledger.records()[0].status == "cancelled"
    assert ledger.records()[0].input_tokens is None


async def test_semantic_failure_still_keeps_usage_and_ledger_is_durable_before_http(tmp_path):
    ledger = ExecutionLedger(tmp_path / "calls.sqlite")

    def handle(req):
        assert len(ExecutionLedger(ledger.path).records()) == 1
        assert ledger.records()[0].status == "started"
        return httpx.Response(200, json=response('{"value": -1}'))

    with execution_scope(ledger, run_id="r", entrypoint="service"):
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
            result = await client.call_model(
                request(),
                validate,
                api_key=SecretStr("fixture"),
                base_url="https://provider.fixture/v1",
                http_client=http,
            )
    assert result.failure.stage == "semantic"
    assert ledger.records()[0].input_tokens == 12
    assert ledger.records()[0].status == "failed"
