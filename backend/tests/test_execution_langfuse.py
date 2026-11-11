"""전송 접수와 저장 검증을 구분하고 재전송의 중복 과금을 방지한다."""

import importlib.util
import json
from dataclasses import replace
from datetime import UTC, datetime

import httpx
import pytest

from tests.test_execution_ledger import call


def api():
    assert importlib.util.find_spec("app.integrations.execution_langfuse") is not None
    from app.integrations import execution_langfuse

    return execution_langfuse


def stored_row(span_id, values):
    return {
        "id": span_id,
        "traceId": values["trace_id"],
        "parentObservationId": values["parent_id"],
        "startTime": datetime.fromtimestamp(values["started_at"], UTC).isoformat(),
        "endTime": datetime.fromtimestamp(values["ended_at"], UTC).isoformat(),
        "metadata": {"ledger_record_sha256": values["record_sha256"]},
        "usageDetails": values["usage"],
        "totalCost": None,
    }


def test_nested_stage_is_exported_as_physical_call_parent():
    parent = replace(call(), call_id="stage-1", kind="stage", status="succeeded", elapsed_seconds=2)
    child = replace(
        call(), call_id="attempt-1", parent_call_id="stage-1", status="succeeded", elapsed_seconds=1
    )
    batch = api().build_export([parent, child])
    spans = batch["payload"]["resourceSpans"][0]["scopeSpans"][0]["spans"]
    stage = next(item for item in spans if item["name"].startswith("stage:"))
    physical = next(item for item in spans if item["name"].startswith("generation:"))
    assert physical["parentSpanId"] == stage["spanId"]
    assert batch["expected"][physical["spanId"]]["parent_id"] == stage["spanId"]


def test_payload_is_stable_namespaces_unverified_prices_and_omits_content():
    m = api()
    record = replace(
        call(actual_model="gpt-6-luna"),
        status="succeeded",
        elapsed_seconds=2,
        input_tokens=100,
        output_tokens=30,
        reasoning_tokens=20,
    )
    batch = m.build_export([record])
    assert batch == m.build_export([record])
    spans = batch["payload"]["resourceSpans"][0]["scopeSpans"][0]["spans"]
    assert len(spans) == 2
    root, leaf = spans
    attributes = {a["key"]: a["value"] for a in leaf["attributes"]}
    assert leaf["parentSpanId"] == root["spanId"]
    assert batch["expected"][leaf["spanId"]]["started_at"] == 1000
    assert batch["expected"][leaf["spanId"]]["ended_at"] == 1002
    assert attributes["langfuse.observation.model.name"]["stringValue"].endswith("::gpt-6-luna")
    assert json.loads(attributes["langfuse.observation.usage_details"]["stringValue"]) == {
        "input": 100,
        "output": 30,
    }
    assert "langfuse.observation.cost_details" not in attributes
    assert "langfuse.observation.usage_details" not in {a["key"] for a in root["attributes"]}
    assert "raw_output" not in json.dumps(batch)


async def test_http_acceptance_does_not_become_durable_success(tmp_path):
    from app.integrations.execution_ledger import ExecutionLedger

    m = api()
    ledger = ExecutionLedger(tmp_path / "ledger.sqlite")
    ledger.start(call())
    ledger.finish(replace(call(), status="failed", elapsed_seconds=1))

    def handle(request):
        if request.method == "POST":
            return httpx.Response(200, json={})
        return httpx.Response(200, json={"data": [], "meta": {}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        result = await m.export_ledger(
            ledger,
            base_url="http://127.0.0.1:13000",
            public_key="pk",
            secret_key="sk",
            http=http,
            readback_attempts=1,
        )
    assert result["accepted"] is True
    assert result["saved_verified"] is False
    assert result["missing_observations"] == 2


async def test_readback_checks_usage_metadata_and_repeated_send_ids(tmp_path):
    from app.integrations.execution_ledger import ExecutionLedger

    m = api()
    ledger = ExecutionLedger(tmp_path / "ledger.sqlite")
    ledger.start(call())
    ledger.finish(
        replace(call(), status="succeeded", elapsed_seconds=2, input_tokens=50, output_tokens=10)
    )
    expected = m.build_export(ledger.records())
    posted_ids = []

    def handle(request):
        if request.method == "POST":
            spans = json.loads(request.content)["resourceSpans"][0]["scopeSpans"][0]["spans"]
            posted_ids.append([s["spanId"] for s in spans])
            return httpx.Response(200, json={})
        if not posted_ids:
            return httpx.Response(200, json={"data": [], "meta": {}})
        data = []
        for span_id, values in expected["expected"].items():
            data.append(stored_row(span_id, values))
        return httpx.Response(200, json={"data": data, "meta": {}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        for _ in range(2):
            result = await m.export_ledger(
                ledger,
                base_url="http://127.0.0.1:13000",
                public_key="pk",
                secret_key="sk",
                http=http,
                readback_attempts=1,
            )
            assert result["saved_verified"] is True
            assert result["verified_observations"] == 2
    assert len(posted_ids) == 1


async def test_duplicate_native_observations_are_not_hidden_by_id_deduplication(tmp_path):
    from app.integrations.execution_ledger import ExecutionLedger

    m = api()
    ledger = ExecutionLedger(tmp_path / "ledger.sqlite")
    ledger.start(call())
    ledger.finish(replace(call(), status="succeeded", elapsed_seconds=2))
    expected = m.build_export(ledger.records())

    def handle(request):
        if request.method == "POST":
            return httpx.Response(200, json={})
        rows = [stored_row(key, value) for key, value in expected["expected"].items()]
        return httpx.Response(200, json={"data": rows + rows, "meta": {}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        result = await m.export_ledger(
            ledger,
            base_url="http://127.0.0.1:13000",
            public_key="pk",
            secret_key="sk",
            http=http,
            readback_attempts=1,
        )
    assert result["saved_verified"] is False
    assert result["duplicate_observation_ids"] == 2


def test_delivery_claim_is_exclusive_and_exported_content_cannot_change(tmp_path):
    from app.integrations.execution_ledger import ExecutionLedger

    ledger = ExecutionLedger(tmp_path / "events.sqlite")
    assert hasattr(ledger, "claim_delivery")
    assert ledger.claim_delivery("target", {"span": "hash-a"}) == {"span"}
    assert ExecutionLedger(ledger.path).claim_delivery("target", {"span": "hash-a"}) == set()
    with pytest.raises(ValueError, match="immutable"):
        ledger.claim_delivery("target", {"span": "hash-b"})


async def test_lost_post_response_is_unknown_and_never_automatically_reposted(tmp_path):
    from app.integrations.execution_ledger import ExecutionLedger

    ledger = ExecutionLedger(tmp_path / "events.sqlite")
    ledger.start(call())
    ledger.finish(replace(call(), status="succeeded", elapsed_seconds=2))
    posts = []

    def handle(request):
        if request.method == "POST":
            posts.append(request)
            raise httpx.RemoteProtocolError("response lost")
        return httpx.Response(200, json={"data": [], "meta": {}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        for _ in range(2):
            receipt = await api().export_ledger(
                ledger,
                base_url="http://127.0.0.1:13000",
                public_key="pk",
                secret_key="sk",
                http=http,
                readback_attempts=1,
            )
            assert receipt["saved_verified"] is False
    assert len(posts) == 1


def test_parallel_delivery_claim_has_only_one_winner(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    from app.integrations.execution_ledger import ExecutionLedger

    ledger = ExecutionLedger(tmp_path / "events.sqlite")

    def claim(_):
        return ExecutionLedger(ledger.path).claim_delivery("target", {"span": "hash"})

    with ThreadPoolExecutor(max_workers=4) as pool:
        claims = list(pool.map(claim, range(4)))
    assert sum(len(result) for result in claims) == 1


async def test_usage_mismatch_is_not_verified(tmp_path):
    from app.integrations.execution_ledger import ExecutionLedger

    m = api()
    ledger = ExecutionLedger(tmp_path / "ledger.sqlite")
    ledger.start(call())
    ledger.finish(
        replace(call(), status="succeeded", elapsed_seconds=2, input_tokens=50, output_tokens=10)
    )
    expected = m.build_export(ledger.records())

    def handle(request):
        if request.method == "POST":
            return httpx.Response(200, json={})
        rows = [
            {**stored_row(key, value), "usageDetails": {"input": 999}}
            for key, value in expected["expected"].items()
        ]
        return httpx.Response(200, json={"data": rows, "meta": {}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        result = await m.export_ledger(
            ledger,
            base_url="http://127.0.0.1:13000",
            public_key="pk",
            secret_key="sk",
            http=http,
            readback_attempts=1,
        )
    assert result["saved_verified"] is False
    assert result["mismatched_observations"] > 0


async def test_verification_only_does_not_post_or_reinvoke_models(tmp_path):
    import inspect

    from app.integrations.execution_ledger import ExecutionLedger

    m = api()
    assert "verify_only" in inspect.signature(m.export_ledger).parameters
    ledger = ExecutionLedger(tmp_path / "ledger.sqlite")
    ledger.start(call())
    ledger.finish(replace(call(), status="succeeded", elapsed_seconds=2))
    expected = m.build_export(ledger.records())

    def handle(request):
        assert request.method == "GET"
        return httpx.Response(
            200,
            json={
                "data": [stored_row(key, value) for key, value in expected["expected"].items()],
                "meta": {},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        result = await m.export_ledger(
            ledger,
            base_url="http://127.0.0.1:13000",
            public_key="pk",
            secret_key="sk",
            http=http,
            readback_attempts=1,
            verify_only=True,
        )
    assert result["saved_verified"] is True
    assert result["model_api_calls"] == 0


@pytest.mark.parametrize(
    "url",
    ["http://external.example", "http://user:pw@localhost:13000", "http://localhost:13000?x=y"],
)
def test_connection_profile_rejects_unsafe_endpoint(url):
    with pytest.raises(ValueError):
        api().validate_base_url(url)
