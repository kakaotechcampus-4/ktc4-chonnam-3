def summarize(
    records: Sequence[CallRecord], *, prices: Sequence[PriceProfile] = ()
) -> dict[str, Any]:
    if len({item.call_id for item in records}) != len(records):
        raise ValueError("duplicate physical call")
    price_map = {(price.provider, price.model): price for price in prices}
    if len(price_map) != len(prices):
        raise ValueError("duplicate price profile")
    calls = [item for item in records if item.kind != "stage"]
    intervals = sorted(
        (item.started_at, item.started_at + item.elapsed_seconds)
        for item in calls
        if item.elapsed_seconds is not None
    )
    active = 0.0
    end = 0.0
    for left, right in intervals:
        active += max(0.0, right - max(left, end))
        end = max(end, right)
    durations = sorted(item.elapsed_seconds for item in calls if item.elapsed_seconds is not None)
    estimates: list[Decimal] = []
    sources: set[str] = set()
    for item in calls:
        price = price_map.get((item.provider, item.actual_model or ""))
        amount = price.estimate(item) if price is not None else None
        if amount is not None:
            estimates.append(amount)
            assert price is not None
            sources.add(price.source)
    unpriced = len(calls) - len(estimates)
    known_cost = sum(estimates, Decimal(0))
    return {
        "schema_version": "execution-metrics.v1",
        "physical_calls": len(calls),
        "stage_count": len(records) - len(calls),
        "statuses": dict(Counter(item.status for item in calls)),
        "by_operation": dict(Counter(item.operation for item in calls)),
        "outcome_scopes": dict(
            Counter(str(item.metadata.get("outcome_scope", "unspecified")) for item in calls)
        ),
        "known_input_tokens": sum(item.input_tokens or 0 for item in calls),
        "known_output_tokens": sum(item.output_tokens or 0 for item in calls),
        "unknown_usage_calls": sum(
            item.input_tokens is None or (item.kind != "embedding" and item.output_tokens is None)
            for item in calls
        ),
        "unfinished_calls": sum(item.status == "started" for item in calls),
        "unknown_duration_calls": len(calls) - len(durations),
        "duration_sum_seconds": sum(durations),
        "active_wall_seconds": active,
        "observed_window_seconds": max((right for _, right in intervals), default=0)
        - min((left for left, _ in intervals), default=0),
        "duration_p50_seconds": durations[math.ceil(len(durations) * 0.5) - 1]
        if durations
        else None,
        "duration_p95_seconds": durations[math.ceil(len(durations) * 0.95) - 1]
        if durations
        else None,
        "estimated_cost_usd": float(known_cost) if calls and not unpriced else None,
        "known_estimated_cost_usd": float(known_cost) if estimates else None,
        "unpriced_calls": unpriced,
        "cost_status": "estimated" if calls and not unpriced else "incomplete",
        "actual_billed_cost_usd": None,
        "pricing_sources": sorted(sources),
    }


def import_http_records(
    admissions: Sequence[dict[str, Any]],
    receipts: Sequence[dict[str, Any]],
    *,
    run_id: str,
    entrypoint: str,
) -> list[CallRecord]:
    def identity(row: dict[str, Any]) -> str:
        return json.dumps(
            [run_id, row["kind"], row["label"], row["request_sha256"], row["dispatched_at"]],
            separators=(",", ":"),
        )

    starts = {identity(row): row for row in admissions}
    if len(starts) != len(admissions):
        raise ValueError("duplicate admission identity")
    finishes: dict[str, dict[str, Any]] = {}
    for row in receipts:
        key = identity(row)
        if key not in starts:
            raise ValueError("unmatched receipt")
        if key in finishes and finishes[key] != row:
            raise ValueError("conflicting receipt")
        finishes[key] = row
    records = []
    for key, admission in starts.items():
        receipt = finishes.get(key)
        embedding = admission["kind"] == "embeddings"
        metadata: dict[str, str | int | bool | None] = {
            "cohort": admission["label"],
            "source_kind": "historical_http",
            "request_bytes": admission.get("request_bytes"),
            "stream": admission.get("stream"),
            "outcome_scope": "http_transport_only",
        }
        record = CallRecord(
            hashlib.sha256(key.encode()).hexdigest(),
            run_id,
            entrypoint,
            "embedding"
            if embedding
            else "judge"
            if admission["label"] == "judge"
            else "repository_generation",
            "embedding" if embedding else "generation",
            admission["dispatched_at"],
            provider="elice_mlapi",
            requested_model=admission["requested_model"],
            request_sha256=admission["request_sha256"],
            metadata=metadata,
        )
        if receipt is not None:
            status = receipt.get("status_code")
            record = replace(
                record,
                status="succeeded" if type(status) is int and 200 <= status < 300 else "failed",
                elapsed_seconds=receipt.get("elapsed_seconds"),
                actual_model=receipt.get("actual_model"),
                error_code=receipt.get("transport_error"),
                metadata={
                    **metadata,
                    "status_code": status,
                    "response_bytes": receipt.get("response_bytes"),
                },
                **usage_details(receipt.get("usage")),
            )
        records.append(record)
    return records
