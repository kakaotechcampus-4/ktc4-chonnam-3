"""저장 장부를 재집계한다. --send를 명시한 경우에만 Langfuse에 전송하며 모델은 호출하지 않는다."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from collections import defaultdict
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

import httpx

from app.integrations.execution_langfuse import export_ledger
from app.integrations.execution_ledger import (
    CallRecord,
    ExecutionLedger,
    PriceProfile,
    import_http_records,
    record_data,
    summarize,
)


def _read_rows(path: Path) -> tuple[list[dict[str, Any]], str]:
    raw = path.read_bytes()
    if len(raw) > 32 * 1024 * 1024:
        raise ValueError("HTTP ledger import exceeds byte limit")
    rows = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
    if any(type(row) is not dict for row in rows):
        raise ValueError("HTTP ledger rows must be objects")
    return rows, hashlib.sha256(raw).hexdigest()


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    source_bindings = {}
    starts_path = getattr(args, "import_admissions", None)
    ends_path = getattr(args, "import_receipts", None)
    records = None
    if bool(starts_path) != bool(ends_path):
        raise ValueError("both HTTP source ledgers are required")
    if starts_path is not None:
        assert ends_path is not None
        if not args.run_id or not args.entrypoint:
            raise ValueError("historical import requires a stable run ID and entrypoint")
        starts, start_hash = _read_rows(starts_path)
        ends, end_hash = _read_rows(ends_path)
        records = import_http_records(starts, ends, run_id=args.run_id, entrypoint=args.entrypoint)
        source_bindings = {"admissions_sha256": start_hash, "receipts_sha256": end_hash}
    elif not args.ledger.is_file():
        raise ValueError("existing execution ledger is required")
    prices = []
    if args.prices is not None:
        prices = [
            PriceProfile(**item) for item in json.loads(args.prices.read_text(encoding="utf-8"))
        ]
    ledger = ExecutionLedger(args.ledger)
    for record in records or []:
        ledger.start(
            replace(
                record,
                status="started",
                elapsed_seconds=None,
                actual_model=None,
                input_tokens=None,
                output_tokens=None,
                cached_input_tokens=None,
                reasoning_tokens=None,
                cache_write_tokens=None,
                metadata={
                    key: value
                    for key, value in record.metadata.items()
                    if key not in {"status_code", "response_bytes"}
                },
            )
        )
        if record.status != "started":
            ledger.finish(record)
    records = ledger.records()
    groups: dict[str, list[CallRecord]] = defaultdict(list)
    for record in records:
        groups[str(record.metadata.get("cohort", record.run_id))].append(record)
    return {
        "schema_version": "execution-report.v1",
        "new_model_api_calls": 0,
        "measurement_scope": (
            "recorded backend calls; excludes uninstrumented services and Codex development usage"
        ),
        "source_bindings": source_bindings,
        "metrics": summarize(records, prices=prices),
        "groups": {key: summarize(items, prices=prices) for key, items in sorted(groups.items())},
        "price_profiles": [asdict(price) for price in prices],
        "records": [record_data(record) for record in records],
    }


async def send_report(args: argparse.Namespace) -> dict[str, Any]:
    if args.langfuse_profile is None:
        raise ValueError("--send requires a private --langfuse-profile")
    profile = json.loads(args.langfuse_profile.read_text(encoding="utf-8"))
    async with httpx.AsyncClient(trust_env=False, follow_redirects=False) as http:
        receipt = await export_ledger(
            ExecutionLedger(args.ledger),
            base_url=profile["base_url"],
            public_key=profile["public_key"],
            secret_key=profile["secret_key"],
            http=http,
            verify_only=getattr(args, "verify_only", False),
        )
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--import-admissions", type=Path)
    parser.add_argument("--import-receipts", type=Path)
    parser.add_argument("--run-id")
    parser.add_argument("--entrypoint")
    parser.add_argument(
        "--prices", type=Path, help="USD 단가·공급자·모델·출처·기준일을 명시한 JSON 목록"
    )
    transmission = parser.add_mutually_exclusive_group()
    transmission.add_argument(
        "--send", action="store_true", help="미전송 기록만 Langfuse로 전송한다"
    )
    transmission.add_argument(
        "--verify-only", action="store_true", help="전송하지 않고 저장 상태만 재확인한다"
    )
    parser.add_argument("--langfuse-profile", type=Path, help="연결 주소·키를 담은 비공개 JSON")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output must be a new file")
    try:
        report = build_report(args)
        if args.send or args.verify_only:
            report["langfuse"] = asyncio.run(send_report(args))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(json.dumps({"error_code": type(error).__name__, "new_model_api_calls": 0}))
        return 1
    print(
        json.dumps(
            {
                "metrics": report["metrics"],
                "langfuse": report.get("langfuse"),
                "new_model_api_calls": 0,
            }
        )
    )
    return 0 if not (args.send or args.verify_only) or report["langfuse"]["saved_verified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
