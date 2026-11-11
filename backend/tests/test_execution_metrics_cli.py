"""기존 장부 가져오기와 평가 실행의 관측 연결이 모델을 중복 호출하지 않는다."""

import argparse
import importlib.util
import json

import pytest


def api():
    assert importlib.util.find_spec("scripts.execution_metrics") is not None
    from scripts import execution_metrics

    return execution_metrics


def test_import_is_offline_reentrant_and_preserves_unknown_cost(tmp_path):
    m = api()
    admission = {
        "kind": "responses",
        "label": "B",
        "request_sha256": "a" * 64,
        "dispatched_at": 1000.0,
        "requested_model": "gpt-6-luna",
        "request_bytes": 123,
    }
    receipt = {
        **admission,
        "status_code": 200,
        "elapsed_seconds": 3,
        "actual_model": "gpt-6-luna",
        "usage": {"input_tokens": 100, "output_tokens": 20},
    }
    source = tmp_path / "starts.jsonl"
    end = tmp_path / "ends.jsonl"
    source.write_text(json.dumps(admission) + "\n", encoding="utf-8")
    end.write_text(json.dumps(receipt) + "\n", encoding="utf-8")
    args = argparse.Namespace(
        ledger=tmp_path / "ledger.sqlite",
        import_admissions=source,
        import_receipts=end,
        run_id="test",
        entrypoint="legacy_eval",
        prices=None,
        send=False,
        langfuse_profile=None,
    )
    for _ in range(2):
        report = m.build_report(args)
        assert report["metrics"]["physical_calls"] == 1
        assert report["metrics"]["estimated_cost_usd"] is None
        assert report["source_bindings"]["admissions_sha256"]
        assert report["new_model_api_calls"] == 0
    assert "source_kind" in json.dumps(report)


def test_import_rejects_unmatched_receipt_before_creating_ledger(tmp_path):
    m = api()
    start = tmp_path / "starts.jsonl"
    end = tmp_path / "ends.jsonl"
    start.write_text("", encoding="utf-8")
    end.write_text(
        json.dumps(
            {"kind": "responses", "label": "B", "request_sha256": "x", "dispatched_at": 1000}
        )
        + "\n",
        encoding="utf-8",
    )
    args = argparse.Namespace(
        ledger=tmp_path / "ledger.sqlite",
        import_admissions=start,
        import_receipts=end,
        run_id="test",
        entrypoint="legacy_eval",
        prices=None,
        send=False,
        langfuse_profile=None,
    )
    with pytest.raises(ValueError, match="unmatched"):
        m.build_report(args)
    assert not args.ledger.exists()


async def test_evaluation_cli_scope_records_real_calls_and_keeps_settings_unchanged(
    tmp_path, monkeypatch
):
    import httpx
    from pydantic import SecretStr

    from app.integrations.execution_ledger import ExecutionLedger
    from app.integrations.llm.client import call_model
    from scripts import run_ai_evaluation as cli
    from tests.integrations.test_llm_client import request, response, validate

    assert hasattr(cli, "_execute"), "평가 CLI의 공통 장부 연결이 아직 없다"
    sent = []

    async def implementation(args):
        def handle(req):
            sent.append(json.loads(req.content))
            return httpx.Response(200, json=response())

        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
            result = await call_model(
                request(),
                validate,
                api_key=SecretStr("key"),
                base_url="https://provider.fixture/v1",
                http_client=http,
            )
        assert result.data == 7
        return {"summary": {}, "cases": []}

    monkeypatch.setattr(cli, "_execute", implementation)
    args = argparse.Namespace(
        execution_ledger=tmp_path / "calls.sqlite",
        execution_provider="elice_mlapi",
        execute=True,
        llm_judge=False,
    )
    report = await cli.execute(args)
    assert report["execution_metrics"]["physical_calls"] == 1
    assert len(sent) == 1
    assert sent[0]["max_output_tokens"] == request().limits.max_output_tokens
    assert len(ExecutionLedger(args.execution_ledger).records()) == 2
    assert report["execution_ledger"]["entrypoint"] == "evaluation_cli"


async def test_validation_does_not_create_execution_ledger(tmp_path, monkeypatch):
    from scripts import run_ai_evaluation as cli

    assert hasattr(cli, "_execute")

    async def implementation(args):
        return {"summary": {"mode": "validation"}}

    monkeypatch.setattr(cli, "_execute", implementation)
    args = argparse.Namespace(
        execution_ledger=tmp_path / "calls.sqlite", execute=False, llm_judge=False
    )
    result = await cli.execute(args)
    assert result["summary"]["mode"] == "validation"
    assert not args.execution_ledger.exists()
