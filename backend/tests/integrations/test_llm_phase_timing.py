"""시간 라벨은 받은 구간만 관측하고 응답·실패·취소의 의미를 바꾸지 않는다."""

import asyncio
import json
from dataclasses import replace

import httpx
import pytest
from pydantic import SecretStr

from app.integrations import execution_langfuse, execution_ledger
from app.integrations.llm import client
from tests.integrations.test_llm_client import request, response, validate

MS_FIELDS = (
    "response_headers_ms",
    "first_sse_event_ms",
    "first_output_text_delta_ms",
    "response_read_ms",
    "response_decode_ms",
    "validation_ms",
)


class Clock:
    value = 100.0

    def now(self):
        return self.value

    def advance(self, milliseconds):
        self.value += milliseconds / 1000


class Chunks(httpx.AsyncByteStream):
    def __init__(self, clock, chunks, *, error=None, entered=None):
        self.clock, self.chunks = clock, chunks
        self.error, self.entered = error, entered

    async def __aiter__(self):
        for milliseconds, chunk in self.chunks:
            self.clock.advance(milliseconds)
            yield chunk
        if self.entered is not None:
            self.entered.set()
            await asyncio.Future()
        if self.error is not None:
            self.clock.advance(15)
            raise self.error


def event(value):
    return ("data: " + json.dumps(value, ensure_ascii=False) + "\r\n\r\n").encode()


def completed():
    return event({"type": "response.completed", "response": response()})


async def invoke(
    tmp_path,
    monkeypatch,
    chunks,
    *,
    stream=True,
    status=200,
    validator=validate,
    response_limit=200000,
):
    clock = chunks.clock
    monkeypatch.setattr(client.time, "monotonic", clock.now)
    monkeypatch.setattr(client.time, "perf_counter", clock.now)
    ledger = execution_ledger.ExecutionLedger(tmp_path / "calls.sqlite")
    sent = []

    def handle(req):
        sent.append(req.content)
        clock.advance(20)
        return httpx.Response(status, stream=chunks, headers={"Retry-After": "0"})

    def checked(raw):
        clock.advance(7)
        return validator(raw)

    item = request()
    item = replace(
        item, limits=replace(item.limits, stream=stream, max_response_bytes=response_limit)
    )
    item = replace(item, max_attempts=1)
    with execution_ledger.execution_scope(ledger, run_id="timing", entrypoint="fixture"):
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
            result = await client.call_model(
                item,
                checked,
                api_key=SecretStr("never-export-key"),
                base_url="https://provider.fixture/v1",
                http_client=http,
            )
    records = ledger.records()
    assert len(records) == len(sent) == 1
    assert b"never-export-key" not in ledger.path.read_bytes()
    return result, records[0], ledger


async def test_stream_milestones_wait_for_complete_events_and_ignore_reasoning(
    tmp_path, monkeypatch
):
    clock = Clock()
    created = event({"type": "response.created"})
    delta = event({"type": "response.output_text.delta", "delta": "한"})
    cut = delta.index("한".encode()) + 1
    chunks = Chunks(
        clock,
        [
            (10, b": ping\r\n\r\n"),
            (20, created[:-2]),
            (30, created[-2:]),
            (40, event({"type": "response.reasoning_summary_text.delta", "delta": "thought"})),
            (50, delta[:cut]),
            (60, delta[cut:] + completed()),
            (70, b"data: [DONE]\n\n"),
        ],
    )
    result, record, _ = await invoke(tmp_path, monkeypatch, chunks)
    assert result.data == 7 and result.attempts[0].raw_output == '{"value": 7}'
    assert record.metadata["response_headers_ms"] == 20
    assert record.metadata["first_sse_event_ms"] == 80
    assert record.metadata["first_output_text_delta_ms"] == 230
    assert record.metadata["response_read_ms"] == 280
    assert record.metadata["response_decode_ms"] == 0
    assert record.metadata["validation_ms"] == 7
    assert record.metadata["response_read_complete"] is True
    assert record.metadata["sse_timing_limited"] is False
    assert record.metadata["response_timing_version"] == 2


async def test_lone_carriage_return_is_a_complete_sse_boundary(tmp_path, monkeypatch):
    created = event({"type": "response.created"})
    _, record, _ = await invoke(
        tmp_path,
        monkeypatch,
        Chunks(
            Clock(),
            [
                (30, created[:-1]),
                (30, created[-1:] + completed()),
            ],
        ),
    )
    assert record.metadata["first_sse_event_ms"] == 50


async def test_events_in_one_chunk_share_receive_time_and_empty_delta_is_not_output(
    tmp_path, monkeypatch
):
    clock = Clock()
    raw = event({"type": "response.created"})
    raw += event({"type": "response.output_text.delta", "delta": ""})
    raw += event({"type": "response.output_text.delta", "delta": "{"}) + completed()
    _, record, _ = await invoke(tmp_path, monkeypatch, Chunks(clock, [(150, raw)]))
    assert record.metadata["first_sse_event_ms"] == 170
    assert record.metadata["first_output_text_delta_ms"] == 170


async def test_completed_only_stream_does_not_invent_first_token_time(tmp_path, monkeypatch):
    _, record, _ = await invoke(tmp_path, monkeypatch, Chunks(Clock(), [(100, completed())]))
    assert record.metadata["first_sse_event_ms"] == 120
    assert record.metadata["first_output_text_delta_ms"] is None
    assert record.metadata["response_read_complete"] is True


async def test_non_stream_durations_and_export_keep_version_without_content(tmp_path, monkeypatch):
    raw = json.dumps(response()).encode()
    result, record, ledger = await invoke(
        tmp_path,
        monkeypatch,
        Chunks(Clock(), [(100, raw)]),
        stream=False,
    )
    assert result.data == 7
    assert record.metadata["first_sse_event_ms"] is None
    assert record.metadata["first_output_text_delta_ms"] is None
    assert record.metadata["response_read_ms"] == 100
    assert record.metadata["validation_ms"] == 7
    assert execution_ledger.ExecutionLedger(ledger.path).records() == [record]
    batch = execution_langfuse.build_export([record])
    spans = batch["payload"]["resourceSpans"][0]["scopeSpans"][0]["spans"]
    physical = next(row for row in spans if row["name"].startswith("generation:"))
    attrs = {row["key"]: row["value"] for row in physical["attributes"]}
    assert attrs["langfuse.observation.metadata.response_timing_version"] == {"intValue": "2"}
    assert attrs["langfuse.observation.metadata.response_read_ms"] == {"intValue": "100"}
    assert "langfuse.observation.metadata.first_output_text_delta_ms" not in attrs
    assert "never-export-key" not in json.dumps(batch)
    assert "provider.fixture" not in json.dumps(batch)


async def test_http_failure_preserves_headers_and_unreached_phases(tmp_path, monkeypatch):
    result, record, _ = await invoke(tmp_path, monkeypatch, Chunks(Clock(), []), status=500)
    assert result.failure.stage == "provider" and record.status == "failed"
    assert record.metadata["response_headers_ms"] == 20
    assert record.metadata["response_read_ms"] is None
    assert record.metadata["response_read_complete"] is None
    assert record.metadata["validation_ms"] is None


@pytest.mark.parametrize("error", [httpx.ReadError("fixture"), asyncio.CancelledError()])
@pytest.mark.parametrize("status", [200, 429])
async def test_interrupted_stream_preserves_partial_milestones(
    tmp_path, monkeypatch, error, status
):
    chunks = Chunks(Clock(), [(50, event({"type": "response.created"}))], error=error)
    if isinstance(error, asyncio.CancelledError):
        with pytest.raises(asyncio.CancelledError):
            await invoke(tmp_path, monkeypatch, chunks, status=status)
        record = execution_ledger.ExecutionLedger(tmp_path / "calls.sqlite").records()[0]
        assert record.status == "cancelled"
    else:
        result, record, _ = await invoke(tmp_path, monkeypatch, chunks, status=status)
        assert result.failure.stage == "provider"
    assert record.metadata["first_sse_event_ms"] == (70 if status == 200 else None)
    assert record.metadata["response_read_ms"] == 65
    assert record.metadata["response_read_complete"] is False
    assert record.metadata["response_decode_ms"] is None
    assert record.metadata["validation_ms"] is None


@pytest.mark.parametrize("capped", [False, True])
async def test_rate_limit_error_body_records_eof_or_byte_cap_without_changing_quota(
    tmp_path, monkeypatch, capped
):
    raw = b'{"error":{"type":"insufficient_quota"}}'
    result, record, _ = await invoke(
        tmp_path,
        monkeypatch,
        Chunks(Clock(), [(100, raw)]),
        status=429,
        response_limit=20 if capped else 200000,
    )
    assert result.failure.stage == "provider" and result.failure.provider_status == 429
    assert record.metadata["response_read_ms"] == 100
    assert record.metadata["response_read_complete"] is (not capped)
    assert record.metadata["first_sse_event_ms"] is None
    assert record.metadata["first_output_text_delta_ms"] is None
    assert record.metadata["validation_ms"] is None
    expected = raw[:20] if capped else raw
    assert result.attempts[0].raw_output == expected.decode()
    assert result.failure.provider_cause == ("unclassified_http" if capped else "quota_exhausted")


async def test_timing_probe_limit_never_changes_authoritative_stream_result(tmp_path, monkeypatch):
    raw = event({"type": "response.created", "padding": "x" * 70000}) + completed()
    result, record, _ = await invoke(tmp_path, monkeypatch, Chunks(Clock(), [(100, raw)]))
    assert result.data == 7 and result.attempts[0].raw_output == '{"value": 7}'
    assert record.metadata["sse_timing_limited"] is True
    assert record.metadata["first_sse_event_ms"] is None
    assert record.metadata["first_output_text_delta_ms"] is None
    assert record.metadata["response_read_complete"] is True


@pytest.mark.parametrize(
    "raw,stage",
    [
        (b"data: not-json\n\n", "provider"),
        (event({"type": "response.completed", "response": response("not-json")}), "parse"),
        (event({"type": "response.completed", "response": response('{"value": -1}')}), "semantic"),
    ],
)
async def test_decode_phase_is_separate_from_validator(tmp_path, monkeypatch, raw, stage):
    result, record, _ = await invoke(tmp_path, monkeypatch, Chunks(Clock(), [(100, raw)]))
    assert record.metadata["response_decode_ms"] == 0
    assert result.failure.stage == stage
    assert record.metadata["validation_ms"] == (7 if stage == "semantic" else None)


@pytest.mark.parametrize("name", MS_FIELDS)
@pytest.mark.parametrize("bad", [-1, True, 1.5, "4"])
def test_timing_metadata_requires_nonnegative_integer_or_null(name, bad):
    with pytest.raises(ValueError):
        execution_ledger.CallRecord(
            "x", "r", "fixture", "task", "generation", 0, metadata={name: bad}
        )


@pytest.mark.parametrize("name", ["response_read_complete", "sse_timing_limited"])
@pytest.mark.parametrize("bad", [0, "true", {}])
def test_timing_flags_are_booleans_or_null(name, bad):
    with pytest.raises(ValueError):
        execution_ledger.CallRecord(
            "x", "r", "fixture", "task", "generation", 0, metadata={name: bad}
        )


@pytest.mark.parametrize("bad", [None, 0, 3, True, "1"])
def test_timing_version_is_exact_and_old_records_do_not_gain_fake_timings(bad):
    with pytest.raises(ValueError):
        execution_ledger.CallRecord(
            "x", "r", "fixture", "task", "generation", 0, metadata={"response_timing_version": bad}
        )
    old = execution_ledger.CallRecord("old", "r", "fixture", "task", "generation", 0)
    assert not any(name in old.metadata for name in (*MS_FIELDS, "response_timing_version"))
