"""고해상도 계측은 과거 시도 시간과 별개이며 v1 원장도 계속 읽는다."""

import json
from dataclasses import replace

import httpx
import pytest
from pydantic import SecretStr

from app.integrations import execution_ledger
from app.integrations.llm import client
from tests.integrations.test_llm_client import request, validate
from tests.integrations.test_llm_phase_timing import Chunks, Clock, completed


async def test_high_resolution_phases_do_not_use_the_legacy_attempt_clock(tmp_path, monkeypatch):
    precise = Clock()
    monkeypatch.setattr(client.time, "monotonic", lambda: 50.0)
    monkeypatch.setattr(client.time, "perf_counter", precise.now)
    ledger = execution_ledger.ExecutionLedger(tmp_path / "calls.sqlite")

    def handle(_request):
        precise.advance(25)
        return httpx.Response(200, stream=Chunks(precise, [(150, completed())]))

    def checked(raw):
        precise.advance(7)
        return validate(raw)

    item = request()
    item = replace(item, limits=replace(item.limits, stream=True), max_attempts=1)
    with execution_ledger.execution_scope(ledger, run_id="qpc", entrypoint="fixture"):
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
            result = await client.call_model(
                item,
                checked,
                api_key=SecretStr("fixture"),
                base_url="https://provider.fixture/v1",
                http_client=http,
            )
    [record] = ledger.records()
    assert result.data == 7
    assert record.metadata["response_timing_version"] == 2
    assert record.metadata["response_headers_ms"] == 25
    assert record.metadata["first_sse_event_ms"] == 175
    assert record.metadata["first_output_text_delta_ms"] is None
    assert record.metadata["response_read_ms"] == 150
    assert record.metadata["response_decode_ms"] == 0
    assert record.metadata["validation_ms"] == 7
    assert result.attempts[0].latency_ms == 0
    assert record.elapsed_seconds == pytest.approx(0.182)


@pytest.mark.parametrize("version", [1, 2])
def test_old_and_new_timing_versions_round_trip_without_rewriting(version):
    record = execution_ledger.CallRecord(
        "x",
        "r",
        "fixture",
        "task",
        "generation",
        0,
        metadata={
            "response_timing_version": version,
            "response_headers_ms": 10,
            "first_output_text_delta_ms": None,
        },
    )
    raw = json.dumps(execution_ledger.record_data(record))
    assert execution_ledger.CallRecord(**json.loads(raw)) == record
    assert record.metadata["response_timing_version"] == version
