"""실행 결과만 비교한다. 생성·Judge를 재호출하거나 사람 승인으로 승격하지 않는다."""

from __future__ import annotations

import math
import statistics
from collections import Counter
from collections.abc import Mapping
from typing import Any, TypeGuard, cast


def _number(value: object) -> TypeGuard[int | float]:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value >= 0
    )


def _delta(before: object, after: object) -> float | None:
    return after - before if _number(before) and _number(after) else None


def _rows(result: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    rows = result.get("cases")
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError("invalid comparison rows")
    indexed = {}
    for row in rows:
        key = row.get("case")
        if not isinstance(key, str) or not key or key in indexed:
            raise ValueError("duplicate or missing comparison case")
        indexed[key] = row
    if not indexed:
        raise ValueError("comparison needs executed cases")
    return indexed


def _verdict(row: Mapping[str, Any]) -> str | None:
    if row.get("status") != "succeeded":
        return None
    for field in ("judge", "diagnostic_judge"):
        judgment = row.get(field)
        if isinstance(judgment, dict) and not judgment.get("failure"):
            verdict = judgment.get("verdict")
            if verdict in {"accept", "reject", "ambiguous"}:
                return str(verdict)
    return None


def _token_total(row: Mapping[str, Any], key: str) -> int | None:
    attempts = row.get("attempts")
    if not isinstance(attempts, list) or not attempts:
        return None
    values = [attempt.get(key) if isinstance(attempt, dict) else None for attempt in attempts]
    if any(type(value) is not int or value < 0 for value in values):
        return None
    return sum(cast(list[int], values))


def _failure_totals(rows: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    failed = [row for row in rows.values() if row.get("status") == "failed"]
    times = [row.get("service_latency_ms") for row in failed]
    result = {
        "cases": len(failed),
        "service_latency_ms": sum(cast(list[float], times)) if all(map(_number, times)) else None,
        "attempt_records": sum(len(row.get("attempts", [])) for row in failed),
    }
    for key in ("input_tokens", "output_tokens"):
        values = [_token_total(row, key) for row in failed]
        result[key] = sum(cast(list[int], values)) if None not in values else None
    return result


def compare_runs(baseline: Mapping[str, Any], candidate: Mapping[str, Any]) -> dict[str, Any]:
    """원문·기준·설정이 같은 쌍만 비교하고 군집·미판정을 별도로 보존한다."""
    left, right = _rows(baseline), _rows(candidate)
    if set(left) != set(right):
        raise ValueError("comparison case set mismatch")
    for key in ("settings_sha256", "cohort_sha256"):
        values = [
            result.get("metadata", {}).get("study", {}).get(key) for result in (baseline, candidate)
        ]
        if not all(isinstance(value, str) and value for value in values) or values[0] != values[1]:
            raise ValueError("comparison experiment mismatch")
    pairs = []
    groups: dict[str, list[float]] = {}
    for key in sorted(left):
        before, after = left[key], right[key]
        for field in ("input_hash", "expectation_hash", "source_group_id"):
            if not before.get(field) or before[field] != after.get(field):
                raise ValueError(f"comparison {field} mismatch")
        succeeded = before.get("status") == after.get("status") == "succeeded"
        times = (before.get("service_latency_ms"), after.get("service_latency_ms"))
        delta = _delta(times[0], times[1]) if succeeded else None
        if delta is not None:
            groups.setdefault(before["source_group_id"], []).append(delta)
        costs = (before.get("cost_usd"), after.get("cost_usd"))
        cost_delta = _delta(costs[0], costs[1])
        record = {
            "case": key,
            "source_group_id": before["source_group_id"],
            "baseline_status": before.get("status"),
            "candidate_status": after.get("status"),
            "baseline_verdict": _verdict(before),
            "candidate_verdict": _verdict(after),
            "service_latency_delta_ms": delta,
            "cost_delta_usd": cost_delta,
            "baseline_attempt_records": len(before.get("attempts", [])),
            "candidate_attempt_records": len(after.get("attempts", [])),
        }
        for token_key in ("input_tokens", "output_tokens"):
            totals = (_token_total(before, token_key), _token_total(after, token_key))
            record[f"{token_key}_delta"] = (
                totals[1] - totals[0] if totals[0] is not None and totals[1] is not None else None
            )
        pairs.append(record)
    deltas = [
        pair["service_latency_delta_ms"]
        for pair in pairs
        if pair["service_latency_delta_ms"] is not None
    ]
    priced = [pair["cost_delta_usd"] for pair in pairs]
    states = Counter(pair["candidate_verdict"] for pair in pairs)
    return {
        "format_version": 1,
        "scope": "paired_director_outputs",
        "pairs": pairs,
        "summary": {
            "paired_cases": len(pairs),
            "timed_success_pairs": len(deltas),
            "source_groups": len({pair["source_group_id"] for pair in pairs}),
            "median_service_latency_delta_ms": statistics.median(deltas) if deltas else None,
            "mean_service_latency_delta_ms": statistics.mean(deltas) if deltas else None,
            "group_mean_latency_deltas_ms": {
                key: statistics.mean(values) for key, values in groups.items()
            },
            "candidate_execution_failures": sum(
                pair["candidate_status"] == "failed" for pair in pairs
            ),
            "baseline_failures": _failure_totals(left),
            "candidate_failures": _failure_totals(right),
            "candidate_quality_passes": states["accept"],
            "candidate_quality_rejects": states["reject"],
            "candidate_quality_ambiguous": states["ambiguous"],
            "candidate_quality_unknown": states[None],
            "quality_regressions": sum(
                pair["baseline_verdict"] == "accept"
                and (pair["candidate_verdict"] == "reject" or pair["candidate_status"] == "failed")
                for pair in pairs
            ),
            "cost_delta_usd": sum(priced) if all(value is not None for value in priced) else None,
            "cost_unknown_pairs": sum(value is None for value in priced),
            "human_review_status": "deferred",
            "release_gate_passed": None,
        },
        "limitations": [
            "같은 source group의 변형과 턴은 독립 표본이 아니다.",
            "Judge 시간과 latency_ms는 서비스 지연 비교에 합산하지 않는다.",
            "attempt_records는 저장된 시도 수이며 미기록 과거 청구 건수의 증거가 아니다.",
            "고정 수치 합격선·통계적 일반화·사람 승인을 이 비교만으로 선언하지 않는다.",
        ],
    }
