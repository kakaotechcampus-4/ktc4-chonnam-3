"""현재 검수 원본과 과거 코호트의 출처를 바꿔 읽지 않는지 검사한다."""

import hashlib
import json
from collections import Counter
from pathlib import Path

import pytest
from eval_cases import Case, CaseError, _history, load_cases
from source_snapshot import SNAPSHOT_DIRECTORY, source_file, validate_bound_sources

ROOT = Path(__file__).parents[1] / "evals"


def test_current_cases_keep_latest_review_status_without_reusing_historical_approval():
    cases = load_cases(ROOT, allow_legacy_report_contracts=True)
    original_ids = {
        *(f"e-{n:04}" for n in range(1, 7)),
        *(f"q-{n:04}" for n in range(1, 11)),
        "f-0001",
        "r-0001",
        "r-0002",
    }
    original = [case for case in cases if case.case_id in original_ids]
    # 새 사례가 추가되어도 기존 검수 상태와 과거 snapshot의 분리는 유지한다.
    assert {case.case_id for case in original} == original_ids
    assert Counter(case.expectation["review"]["status"] for case in original) == {
        "approved": 6,
        "pending": 4,
        "unreviewed": 9,
    }
    assert all(
        case.expectation["review"]["status"] == "unreviewed"
        for case in cases
        if case.case_id not in original_ids
    )
    with pytest.raises(CaseError, match="Historical"):
        load_cases(ROOT / SNAPSHOT_DIRECTORY, allow_legacy_report_contracts=True)


def test_legacy_contract_exception_requires_an_explicit_review_call():
    turn = {"turn": 1, "persona": "tech_lead", "question": "why", "answer": "because"}
    case = Case("r", 1, "report", "dev", "source", {"history": [turn]}, {})
    with pytest.raises(CaseError, match="question_contract"):
        _history(case)
    assert _history(case, allow_legacy_report_contracts=True) == [turn]
    case.payload.update(
        service_task="report",
        service_input={"turns": [{**turn, "turn_no": 1}]},
    )
    with pytest.raises(CaseError, match="question_contract"):
        _history(case, allow_legacy_report_contracts=True)


def _snapshot(tmp_path):
    archive = tmp_path / SNAPSHOT_DIRECTORY
    path = archive / "inputs/old.v1.json"
    path.parent.mkdir(parents=True)
    content = b'{"historical":true}\n'
    path.write_bytes(content)
    digest = hashlib.sha256(content).hexdigest()
    metadata = {
        "schema_version": "historical-eval-snapshot.v1",
        "purpose": "binding_source_only",
        "current_gold": False,
        "files": {"inputs/old.v1.json": digest},
    }
    (archive / "provenance.json").write_text(json.dumps(metadata), encoding="utf-8")
    cohort = tmp_path / "cohort"
    cohort.mkdir()
    manifest = {
        "source_snapshot": SNAPSHOT_DIRECTORY,
        "original_files": {"ai/evals/inputs/old.v1.json": digest},
    }
    (cohort / "binding-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return cohort, manifest, path


def test_snapshot_resolver_uses_the_declared_historical_text(tmp_path):
    cohort, manifest, path = _snapshot(tmp_path)
    assert source_file(cohort, manifest, "ai/evals/inputs/old.v1.json") == path
    validate_bound_sources(cohort)


@pytest.mark.parametrize("relative", ["../old.json", "/outside.json", "C:/outside.json"])
def test_snapshot_resolver_rejects_paths_outside_the_declared_sources(tmp_path, relative):
    cohort, manifest, _ = _snapshot(tmp_path)
    with pytest.raises(ValueError, match="provenance"):
        source_file(cohort, manifest, relative)


def test_snapshot_resolver_rejects_another_snapshot_instead_of_substituting_it(tmp_path):
    cohort, manifest, _ = _snapshot(tmp_path)
    with pytest.raises(ValueError, match="snapshot"):
        source_file(cohort, {**manifest, "source_snapshot": "another"}, "inputs/old.v1.json")


def test_snapshot_mutation_is_rejected_before_case_loading(tmp_path):
    cohort, _, path = _snapshot(tmp_path)
    path.write_bytes(b'{"historical":false}\n')
    with pytest.raises(ValueError, match="snapshot changed"):
        validate_bound_sources(cohort)


def test_bound_fingerprint_mismatch_is_not_accepted_as_a_new_source(tmp_path):
    cohort, manifest, _ = _snapshot(tmp_path)
    manifest["original_files"]["ai/evals/inputs/old.v1.json"] = "0" * 64
    (cohort / "binding-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="fingerprint"):
        validate_bound_sources(cohort)


@pytest.mark.parametrize("damage", ["missing", "json", "array", "files", "digest"])
def test_invalid_archive_metadata_has_one_public_error(tmp_path, damage):
    cohort, _, _ = _snapshot(tmp_path)
    marker = cohort.parent / SNAPSHOT_DIRECTORY / "provenance.json"
    if damage == "missing":
        marker.unlink()
    elif damage == "json":
        marker.write_text("{", encoding="utf-8")
    elif damage == "array":
        marker.write_text("[]", encoding="utf-8")
    else:
        metadata = json.loads(marker.read_text(encoding="utf-8"))
        if damage == "files":
            metadata.pop("files")
        else:
            metadata["files"] = {"inputs/old.v1.json": 1}
        marker.write_text(json.dumps(metadata), encoding="utf-8")
    with pytest.raises(ValueError, match="^Invalid historical source snapshot$"):
        validate_bound_sources(cohort)
