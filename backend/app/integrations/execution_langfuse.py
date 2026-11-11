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
