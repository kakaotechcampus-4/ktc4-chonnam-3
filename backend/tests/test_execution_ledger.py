"""물리 시도·누락·병렬 시간과 재집계의 실제 경계를 검증한다."""

import importlib.util
import json
from dataclasses import replace

import pytest


def api():
    assert importlib.util.find_spec("app.integrations.execution_ledger") is not None, (
        "공통 실행 장부가 아직 없다"
    )
    from app.integrations import execution_ledger

    return execution_ledger


def call(call_id="a", **changes):
    return api().CallRecord(
        call_id=call_id,
        run_id="run",
        entrypoint="evaluation_cli",
        operation="repo_shallow",
        kind="generation",
        started_at=1000.0,
        **changes,
    )


def test_persisted_attempt_is_unknown_until_finished_and_reopen_is_idempotent(tmp_path):
    m = api()
    path = tmp_path / "ledger.sqlite"
    ledger = m.ExecutionLedger(path)
    started = call(requested_model="gpt-6-luna")
    ledger.start(started)
    assert m.summarize(ledger.records())["unknown_usage_calls"] == 1
    finished = replace(
        started, status="succeeded", elapsed_seconds=2.0, input_tokens=100, output_tokens=20
    )
    ledger.finish(finished)
    ledger.finish(finished)
    reopened = m.ExecutionLedger(path)
    assert reopened.records() == [finished]
    assert reopened.event_count() == 2
    with pytest.raises(ValueError, match="conflict"):
        reopened.finish(replace(finished, input_tokens=101))


def test_identical_request_retries_are_distinct_and_cost_is_not_zero_when_unpriced():
    m = api()
    records = [
        replace(call(key, request_sha256="same"), status="failed", elapsed_seconds=1)
        for key in ("a", "b")
    ]
    report = m.summarize(records)
    assert report["physical_calls"] == 2
    assert report["unknown_usage_calls"] == 2
    assert report["estimated_cost_usd"] is None
    assert report["unpriced_calls"] == 2
    with pytest.raises(ValueError, match="duplicate"):
        m.summarize([records[0], records[0]])


def test_parallel_wall_union_and_duration_sum_are_separate():
    m = api()
    records = [
        replace(call("a"), status="succeeded", elapsed_seconds=10),
        replace(call("b"), status="succeeded", started_at=1005, elapsed_seconds=10),
        replace(call("c"), status="failed", started_at=1020, elapsed_seconds=2),
    ]
    report = m.summarize(records)
    assert report["duration_sum_seconds"] == 22
    assert report["active_wall_seconds"] == 17
    assert report["observed_window_seconds"] == 22
    assert report["duration_p50_seconds"] == 10
    assert report["unfinished_calls"] == 0


def test_reasoning_is_not_added_again_and_cached_input_uses_explicit_rate():
    m = api()
    item = replace(
        call(actual_model="luna", provider="elice"),
        status="succeeded",
        input_tokens=1000,
        output_tokens=200,
        cached_input_tokens=400,
        reasoning_tokens=150,
    )
    price = m.PriceProfile(
        provider="elice",
        model="luna",
        input_per_million="2",
        output_per_million="10",
        cached_input_per_million="1",
        source="account-price-snapshot",
        as_of="2026-11-10",
    )
    report = m.summarize([item], prices=[price])
    assert report["known_output_tokens"] == 200
    assert report["estimated_cost_usd"] == pytest.approx(0.0036)
    assert report["cost_status"] == "estimated"
    assert report["actual_billed_cost_usd"] is None
    assert report["pricing_sources"] == ["account-price-snapshot"]


def test_unknown_cache_breakdown_prevents_different_cache_rate_estimate():
    m = api()
    price = m.PriceProfile(
        provider="elice",
        model="luna",
        input_per_million="2",
        output_per_million="10",
        cached_input_per_million="1",
        source="account-price-snapshot",
        as_of="2026-11-10",
    )
    item = replace(call(actual_model="luna", provider="elice"), input_tokens=100, output_tokens=10)
    assert m.summarize([item], prices=[price])["estimated_cost_usd"] is None


@pytest.mark.parametrize("bad", [True, -1, 1.5, float("nan")])
def test_invalid_token_counts_are_rejected(bad):
    with pytest.raises(ValueError):
        call(input_tokens=bad)


def test_stage_is_in_timing_but_never_added_to_model_call_cost():
    m = api()
    stage = replace(call("stage"), kind="stage", status="succeeded", elapsed_seconds=30)
    model = replace(
        call(), status="succeeded", elapsed_seconds=10, input_tokens=20, output_tokens=5
    )
    report = m.summarize([stage, model])
    assert report["physical_calls"] == 1
    assert report["stage_count"] == 1
    assert report["duration_sum_seconds"] == 10
    assert report["known_input_tokens"] == 20


def test_historical_import_matches_physical_identity_and_keeps_missing_receipts_unknown(tmp_path):
    m = api()
    row = dict(
        kind="responses",
        label="B",
        request_sha256="same",
        dispatched_at=1000,
        requested_model="gpt-6-luna",
        stream=True,
        request_bytes=30,
    )
    retry = {**row, "dispatched_at": 1001}
    receipt = {
        **row,
        "elapsed_seconds": 2,
        "status_code": 200,
        "actual_model": "gpt-6-luna",
        "usage": {
            "input_tokens": 100,
            "output_tokens": 20,
            "input_tokens_details": {"cached_tokens": 40},
            "output_tokens_details": {"reasoning_tokens": 15},
        },
    }
    records = m.import_http_records([row, retry], [receipt], run_id="r", entrypoint="legacy_eval")
    assert len({r.call_id for r in records}) == 2
    assert records[0].reasoning_tokens == 15
    assert records[1].status == "started"
    assert m.summarize(records)["unknown_usage_calls"] == 1
    assert "Authorization" not in json.dumps([m.record_data(r) for r in records])
    with pytest.raises(ValueError, match="unmatched"):
        m.import_http_records(
            [row], [{**receipt, "dispatched_at": 999}], run_id="r", entrypoint="x"
        )


async def test_scoped_recording_captures_cancellation_and_avoids_secret_metadata(tmp_path):
    import asyncio

    m = api()
    ledger = m.ExecutionLedger(tmp_path / "events.sqlite")
    with m.execution_scope(ledger, run_id="run", entrypoint="service", provider="elice"):
        with pytest.raises(asyncio.CancelledError):
            async with m.observe_call("director", requested_model="luna"):
                raise asyncio.CancelledError()
    record = ledger.records()[0]
    assert record.status == "cancelled"
    assert record.elapsed_seconds >= 0
    assert record.input_tokens is None
    assert record.entrypoint == "service"


async def test_unscoped_observation_creates_no_files_or_settings():
    async with api().observe_call("director", requested_model="luna") as observed:
        assert observed is None


@pytest.mark.parametrize("rate", ["bad", True, None])
def test_price_profile_rejects_invalid_rate_types_without_inventing_price(rate):
    with pytest.raises(ValueError):
        api().PriceProfile(
            provider="elice",
            model="luna",
            input_per_million=rate,
            output_per_million="1",
            source="price-snapshot",
            as_of="2026-11-10",
        )


async def test_recorded_interval_includes_start_persistence_time(tmp_path, monkeypatch):
    import time

    m = api()
    ledger = m.ExecutionLedger(tmp_path / "events.sqlite")
    original = ledger.start

    def slow_start(record):
        time.sleep(0.03)
        original(record)

    monkeypatch.setattr(ledger, "start", slow_start)
    with m.execution_scope(ledger, run_id="r", entrypoint="service"):
        async with m.observe_call("director"):
            pass
    assert ledger.records()[0].elapsed_seconds >= 0.03
