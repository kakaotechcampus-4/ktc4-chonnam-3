"""저장된 실행 장부만 OTLP로 전송하고 관측 ID·지문·사용량을 다시 읽어 확인한다."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Sequence
from datetime import datetime
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.integrations.execution_ledger import CallRecord, ExecutionLedger, record_data


def validate_base_url(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or any(char.isspace() for char in value)
        or parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.scheme == "http"
        and parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
    ):
        raise ValueError(
            "Langfuse requires HTTPS or an explicit loopback address without credentials"
        )
    _ = parsed.port
    return value.rstrip("/")


def _hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()
    ).hexdigest()


def _attribute(key: str, value: object) -> dict[str, Any]:
    encoded: dict[str, Any]
    if type(value) is bool:
        encoded = {"boolValue": value}
    elif type(value) is int:
        encoded = {"intValue": str(value)}
    elif type(value) is float:
        encoded = {"doubleValue": value}
    else:
        encoded = {
            "stringValue": value if isinstance(value, str) else json.dumps(value, sort_keys=True)
        }
    return {"key": key, "value": encoded}


def build_export(records: Sequence[CallRecord]) -> dict[str, Any]:
    if len({record.call_id for record in records}) != len(records):
        raise ValueError("duplicate ledger call")
    groups: dict[str, list[CallRecord]] = defaultdict(list)
    for record in records:
        if record.elapsed_seconds is not None:
            groups[record.run_id].append(record)
    spans: list[dict[str, Any]] = []
    expected: dict[str, Any] = {}
    for run_id, items in sorted(groups.items()):
        trace_id = _hash(["execution-ledger.v1", run_id])[:32]
        root_id = _hash(["root", run_id])[:16]
        start = min(item.started_at for item in items)
        end = max(item.started_at + (item.elapsed_seconds or 0) for item in items)
        root_hash = _hash(
            [record_data(item) for item in sorted(items, key=lambda item: item.call_id)]
        )
        root = {
            "traceId": trace_id,
            "spanId": root_id,
            "name": "observed execution window",
            "startTimeUnixNano": str(int(start * 1_000_000_000)),
            "endTimeUnixNano": str(int(end * 1_000_000_000)),
            "attributes": [
                _attribute("langfuse.observation.type", "span"),
                _attribute("langfuse.trace.name", run_id),
                _attribute("langfuse.observation.metadata.ledger_record_sha256", root_hash),
                _attribute(
                    "langfuse.observation.metadata.timing_scope", "observed recorded calls only"
                ),
            ],
        }
        spans.append(root)
        expected[root_id] = {
            "trace_id": trace_id,
            "record_sha256": root_hash,
            "usage": {},
            "parent_id": None,
            "started_at": start,
            "ended_at": end,
        }
        for item in sorted(items, key=lambda item: (item.started_at, item.call_id)):
            span_id = _hash(["call", item.call_id])[:16]
            parent_id = (
                _hash(["call", item.parent_call_id])[:16]
                if any(parent.call_id == item.parent_call_id for parent in items)
                else root_id
            )
            record_hash = _hash(record_data(item))
            usage = {}
            if item.kind != "stage":
                if item.input_tokens is not None:
                    usage["input"] = item.input_tokens
                if item.output_tokens is not None:
                    usage["output"] = item.output_tokens
            attributes: dict[str, object] = {
                "langfuse.trace.name": run_id,
                "langfuse.observation.type": "span" if item.kind == "stage" else item.kind,
                "langfuse.observation.level": "ERROR"
                if item.status in {"failed", "cancelled"}
                else "DEFAULT",
                "langfuse.observation.metadata.ledger_record_sha256": record_hash,
                "langfuse.observation.metadata.call_id": item.call_id,
                "langfuse.observation.metadata.entrypoint": item.entrypoint,
                "langfuse.observation.metadata.operation": item.operation,
                "langfuse.observation.metadata.status": item.status,
                "langfuse.observation.metadata.cost_status": "unpriced",
                "langfuse.observation.metadata.content_exported": False,
                "langfuse.observation.metadata.actual_model": item.actual_model,
                "langfuse.observation.metadata.requested_model": item.requested_model,
                "langfuse.observation.metadata.cached_input_tokens": item.cached_input_tokens,
                "langfuse.observation.metadata.reasoning_tokens": item.reasoning_tokens,
                "langfuse.observation.metadata.cache_write_tokens": item.cache_write_tokens,
                **{
                    "langfuse.observation.metadata." + key: value
                    for key, value in item.metadata.items()
                },
            }
            model = item.actual_model or item.requested_model
            if model is not None and item.kind != "stage":
                # 공급자 단가 검증 전에는 동명 OpenAI 기본 단가의 자동 적용을 막는다.
                attributes["langfuse.observation.model.name"] = item.provider + "::" + model
            if usage:
                attributes["langfuse.observation.usage_details"] = usage
            spans.append(
                {
                    "traceId": trace_id,
                    "spanId": span_id,
                    "parentSpanId": parent_id,
                    "name": item.kind + ":" + item.operation,
                    "startTimeUnixNano": str(int(item.started_at * 1_000_000_000)),
                    "endTimeUnixNano": str(
                        int((item.started_at + (item.elapsed_seconds or 0)) * 1_000_000_000)
                    ),
                    "attributes": [
                        _attribute(key, value)
                        for key, value in attributes.items()
                        if value is not None
                    ],
                    "status": {"code": 2 if item.status in {"failed", "cancelled"} else 1},
                }
            )
            expected[span_id] = {
                "trace_id": trace_id,
                "record_sha256": record_hash,
                "usage": usage,
                "parent_id": parent_id,
                "started_at": item.started_at,
                "ended_at": item.started_at + (item.elapsed_seconds or 0),
            }
    payload = {
        "resourceSpans": [
            {
                "resource": {"attributes": [_attribute("service.name", "devon.execution-ledger")]},
                "scopeSpans": [
                    {"scope": {"name": "devon.execution-ledger", "version": "1"}, "spans": spans}
                ],
            }
        ]
    }
    return {
        "payload": payload,
        "expected": expected,
        "export_id": _hash(expected),
        "unexported_unknown_duration": sum(record.elapsed_seconds is None for record in records),
    }


async def _readback(
    http: httpx.AsyncClient, base_url: str, auth: httpx.BasicAuth, expected: dict[str, Any]
) -> dict[str, int]:
    rows: dict[str, dict[str, Any]] = {}
    counts: Counter[str] = Counter()
    for trace_id in sorted({item["trace_id"] for item in expected.values()}):
        cursor = None
        seen = set()
        for _ in range(100):
            params = {"traceId": trace_id, "limit": "1000", "fields": "core,basic,usage,metadata"}
            if cursor:
                params["cursor"] = cursor
            response = await http.get(
                base_url + "/api/public/v2/observations",
                params=params,
                auth=auth,
                timeout=10,
                follow_redirects=False,
            )
            response.raise_for_status()
            result = response.json()
            for row in result["data"]:
                counts[row["id"]] += 1
                rows[row["id"]] = row
            cursor = result.get("meta", {}).get("cursor")
            if not cursor:
                break
            if cursor in seen:
                raise ValueError("repeated observation cursor")
            seen.add(cursor)
        else:
            raise ValueError("observation page limit exceeded")
    verified = mismatched = missing = 0
    for span_id, item in expected.items():
        row = rows.get(span_id)
        if row is None:
            missing += 1
            continue
        usage = {
            key: value for key, value in (row.get("usageDetails") or {}).items() if key != "total"
        }
        timing_matches = True
        for field, source in (("startTime", "started_at"), ("endTime", "ended_at")):
            stamp = row.get(field)
            try:
                if not isinstance(stamp, str):
                    raise ValueError("missing timestamp")
                timing_matches &= (
                    abs(datetime.fromisoformat(stamp).timestamp() - item[source]) <= 0.002
                )
            except (ValueError, TypeError, OverflowError):
                timing_matches = False
        if (
            row.get("traceId") != item["trace_id"]
            or counts[span_id] != 1
            or row.get("parentObservationId") != item["parent_id"]
            or not timing_matches
            or (row.get("metadata") or {}).get("ledger_record_sha256") != item["record_sha256"]
            or usage != item["usage"]
            or row.get("totalCost") is not None
        ):
            mismatched += 1
        else:
            verified += 1
    return {
        "verified_observations": verified,
        "mismatched_observations": mismatched,
        "missing_observations": missing,
        "duplicate_observation_ids": sum(count > 1 for count in counts.values()),
        "observations_returned": sum(counts.values()),
        "unexpected_observations": len(set(rows) - set(expected)),
    }


async def export_ledger(
    ledger: ExecutionLedger,
    *,
    base_url: str,
    public_key: str,
    secret_key: str,
    http: httpx.AsyncClient,
    readback_attempts: int = 5,
    verify_only: bool = False,
) -> dict[str, Any]:
    base_url = validate_base_url(base_url)
    if not public_key or not secret_key or not 1 <= readback_attempts <= 10:
        raise ValueError("invalid export configuration")
    batch = build_export(ledger.records())
    if not batch["expected"]:
        raise ValueError("no completed observations to export")
    if batch["unexported_unknown_duration"]:
        raise ValueError("finish the execution before exporting immutable observations")
    target = _hash([base_url, public_key])
    bindings = {key: value["record_sha256"] for key, value in batch["expected"].items()}
    states = ledger.delivery_states(target)
    receipt = {
        "schema_version": "execution-export.v1",
        "export_id": batch["export_id"],
        "accepted": all(states.get(key) == "accepted" for key in bindings),
        "saved_verified": False,
        "verified_observations": 0,
        "expected_observations": len(batch["expected"]),
        "missing_observations": len(batch["expected"]),
        "mismatched_observations": 0,
        "trace_ids": sorted({item["trace_id"] for item in batch["expected"].values()}),
        "unexported_unknown_duration": batch["unexported_unknown_duration"],
        "model_api_calls": 0,
        "verification_only": verify_only,
        "new_http_posts": 0,
    }
    ledger.save_export(batch["export_id"], receipt)
    auth = httpx.BasicAuth(public_key, secret_key)
    claimed: set[str] = set()
    try:
        # v4는 같은 span ID를 다시 보내도 새 행을 쓴다. 먼저 기존 저장 여부를 확인한다.
        preflight = await _readback(http, base_url, auth, batch["expected"])
        receipt.update(preflight)
        conflict = any(
            preflight[key]
            for key in (
                "mismatched_observations",
                "duplicate_observation_ids",
                "unexpected_observations",
            )
        )
        if conflict:
            receipt["error_code"] = "immutable_observation_conflict"
            ledger.save_export(batch["export_id"], receipt)
            return receipt
        if not verify_only and preflight["missing_observations"] == len(bindings):
            claimed = ledger.claim_delivery(target, bindings)
            if claimed:
                # 한 배치의 부분 접수·응답 유실은 조회로만 복구한다. 전체를 다시 보내지 않는다.
                spans = batch["payload"]["resourceSpans"][0]["scopeSpans"][0]["spans"]
                batch["payload"]["resourceSpans"][0]["scopeSpans"][0]["spans"] = [
                    span for span in spans if span["spanId"] in claimed
                ]
                receipt["new_http_posts"] = 1
                response = await http.post(
                    base_url + "/api/public/otel/v1/traces",
                    json=batch["payload"],
                    auth=auth,
                    headers={"x-langfuse-ingestion-version": "4"},
                    timeout=15,
                    follow_redirects=False,
                )
                response.raise_for_status()
                body = response.json()
                if int(body.get("partialSuccess", {}).get("rejectedSpans", 0)):
                    raise ValueError("Langfuse rejected spans")
                receipt["accepted"] = True
                ledger.mark_delivery(target, list(claimed), "accepted")
        for attempt in range(readback_attempts):
            result = await _readback(http, base_url, auth, batch["expected"])
            receipt.update(result)
            receipt["saved_verified"] = result["verified_observations"] == len(
                bindings
            ) and not any(
                result[key]
                for key in (
                    "mismatched_observations",
                    "missing_observations",
                    "duplicate_observation_ids",
                    "unexpected_observations",
                )
            )
            if receipt["saved_verified"]:
                receipt["accepted"] = True
                ledger.claim_delivery(target, bindings)
                ledger.mark_delivery(target, list(bindings), "accepted")
                break
            if attempt + 1 < readback_attempts:
                await asyncio.sleep(min(2**attempt, 8))
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as error:
        receipt["error_code"] = type(error).__name__
        receipt["saved_verified"] = False
        if claimed and not receipt["accepted"]:
            ledger.mark_delivery(target, list(claimed), "unknown")
    ledger.save_export(batch["export_id"], receipt)
    return receipt
