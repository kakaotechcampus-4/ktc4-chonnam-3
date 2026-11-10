"""평가 지문·종료 상태·중단 기록은 공급자 호출 없이 검사한다."""

import asyncio
import json
import sys
import threading

import pytest

from scripts import run_ai_evaluation as cli


def arguments(monkeypatch, tmp_path):
    output = tmp_path / "result.json"
    monkeypatch.setattr(
        sys,
        "argv",
        ["evaluation", "--cases", str(tmp_path), "--manifest", "unused", "--output", str(output)],
    )
    return output


def test_existing_output_is_rejected_before_execution(monkeypatch, tmp_path):
    output = arguments(monkeypatch, tmp_path)
    output.write_bytes(b"original paid result\n")

    async def forbidden(args):
        pytest.fail("existing output must be rejected before execution")

    monkeypatch.setattr(cli, "execute", forbidden)
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 2
    assert output.read_bytes() == b"original paid result\n"


def test_case_failure_returns_nonzero_without_becoming_quality_approval(monkeypatch, tmp_path):
    output = arguments(monkeypatch, tmp_path)

    async def failed(args):
        return {
            "cases": [{"case": "one", "status": "failed"}],
            "summary": {"total": 1, "statuses": {"failed": 1}, "release_gate_passed": None},
        }

    monkeypatch.setattr(cli, "execute", failed)
    assert cli.main() == 1
    saved = json.loads(output.read_text("utf-8"))
    assert saved["run_state"] == "completed"
    assert saved["summary"]["release_gate_passed"] is None


def test_input_validation_success_is_not_blocked_by_deferred_human_review(monkeypatch, tmp_path):
    output = arguments(monkeypatch, tmp_path)

    async def validated(args):
        return {
            "cases": [{"case": "one", "status": "validated_only"}],
            "summary": {"total": 1, "statuses": {"validated_only": 1}, "release_gate_passed": None},
        }

    monkeypatch.setattr(cli, "execute", validated)
    assert cli.main() == 0
    assert json.loads(output.read_text("utf-8"))["summary"]["release_gate_passed"] is None


def test_cancellation_keeps_completed_case_and_marks_interruption(monkeypatch, tmp_path):
    output = arguments(monkeypatch, tmp_path)

    async def interrupted(args):
        await args._checkpoint(
            {"cases": [{"case": "one", "status": "succeeded"}], "summary": {"completed": 1}}
        )
        raise asyncio.CancelledError

    monkeypatch.setattr(cli, "execute", interrupted)
    with pytest.raises(asyncio.CancelledError):
        cli.main()
    saved = json.loads(output.read_text("utf-8"))
    assert saved["run_state"] == "interrupted"
    assert saved["cases"] == [{"case": "one", "status": "succeeded"}]


def test_dataset_portable_identity_preserves_raw_audit_and_legacy_rules(tmp_path):
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    case = inputs / "case.json"
    case.write_bytes(b'{"input": true}\n')
    lf = cli.dataset_metadata(tmp_path)
    legacy = cli.dataset_metadata(tmp_path, hash_format="raw-v1")
    case.write_bytes(b'{"input": true}\r\n')
    crlf = cli.dataset_metadata(tmp_path)
    assert lf["file_hash_format"] == "utf8_lf"
    assert lf["files"] == crlf["files"] and lf["sha256"] == crlf["sha256"]
    assert lf["raw_files"] != crlf["raw_files"]
    assert cli.dataset_matches(lf, tmp_path)
    assert not cli.dataset_matches(legacy, tmp_path)
    assert not cli.dataset_matches(
        {key: value for key, value in lf.items() if key != "raw_files"}, tmp_path
    )
    assert not cli.dataset_matches({**lf, "raw_sha256": "0" * 64}, tmp_path)


def test_source_has_portable_identity_without_relabeling_existing_raw_hashes(monkeypatch, tmp_path):
    source = tmp_path / "backend/app/fixture.py"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"value = 1\n")
    monkeypatch.setattr(cli, "REPO_ROOT", tmp_path)
    lf = cli.source_metadata()
    source.write_bytes(b"value = 1\r\n")
    crlf = cli.source_metadata()
    assert lf["source_files"] != crlf["source_files"]
    assert lf["portable_source_files"] == crlf["portable_source_files"]
    assert lf["portable_working_source_sha256"] == crlf["portable_working_source_sha256"]


def test_output_reservation_is_exclusive(tmp_path):
    output = tmp_path / "result.json"
    cli.RunOutput(output)
    before = output.read_bytes()
    with pytest.raises(FileExistsError):
        cli.RunOutput(output)
    assert output.read_bytes() == before


@pytest.mark.asyncio
async def test_cancellation_waits_for_checkpoint_writer_before_final_interruption(
    monkeypatch, tmp_path
):
    output = cli.RunOutput(tmp_path / "result.json")
    started, release = threading.Event(), threading.Event()
    original = output.save

    def delayed(result, state):
        started.set()
        assert release.wait(2)
        original(result, state)

    monkeypatch.setattr(output, "save", delayed)
    pending = asyncio.create_task(output.checkpoint({"cases": [{"case": "one"}]}))
    try:
        assert await asyncio.to_thread(started.wait, 2)
        pending.cancel()
        await asyncio.sleep(0)
        assert not pending.done()
    finally:
        release.set()
    with pytest.raises(asyncio.CancelledError):
        await pending
    output.stop("interrupted", "CancelledError")
    saved = json.loads(output.path.read_text("utf-8"))
    assert saved["run_state"] == "interrupted"
    assert saved["cases"] == [{"case": "one"}]


@pytest.mark.asyncio
async def test_current_runtime_manifest_validates_typed_cases_without_provider_settings(
    monkeypatch,
):
    from tests.test_ai_evaluation_cli import ROOT, args

    def forbidden():
        pytest.fail("input validation must not load provider settings")

    monkeypatch.setattr(cli, "get_settings", forbidden)
    dataset = ROOT / "ai/evals/service_regression"
    manifest = dataset / "runtime-manifest.json"
    prompts, _, _ = cli.load_manifest(manifest)
    assert {task: prompts[task].version for task in prompts} == {
        "director": "director_v8",
        "answer_analysis": "answer_analysis_v6",
        "report": "report_v4",
        "report_score": "report_score_v3",
    }
    result = await cli.execute(
        args(cases=dataset, manifest=manifest, split="all", approved_only=False)
    )
    assert result["summary"]["statuses"] == {"validated_only": 32}
    assert result["summary"]["automatic_checks"]["input_contract"]["status"] == "passed"
    assert result["summary"]["human_review_status"] == "deferred"


@pytest.mark.asyncio
async def test_interrupted_output_is_not_rejudged_or_sent_to_a_provider(monkeypatch, tmp_path):
    from tests.test_ai_evaluation_cli import ROOT, args

    def forbidden():
        pytest.fail("interrupted input must be rejected before provider settings")

    monkeypatch.setattr(cli, "get_settings", forbidden)
    previous = tmp_path / "interrupted.json"
    previous.write_text(json.dumps({"run_state": "interrupted", "cases": []}), "utf-8")
    dataset = ROOT / "ai/evals/service_regression"
    with pytest.raises(ValueError, match="completed result"):
        await cli.execute(
            args(
                cases=dataset,
                manifest=dataset / "runtime-manifest.json",
                split="all",
                approved_only=False,
                rejudge_results=previous,
                llm_judge=True,
                max_judge_attempts=1,
            )
        )
