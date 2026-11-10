"""원본 v1의 전역 자료를 새 합성 보고서 입력에 명시적으로 보존한다."""

import hashlib
import json
from pathlib import Path

import pytest
from eval_cases import load_cases
from source_snapshot import source_file

ROOT = Path(__file__).parents[1] / "evals"
COHORT = ROOT / "report_source_binding_cohort"


def test_report_source_cohort_preserves_raw_materials_and_declares_new_available_binding():
    cases = load_cases(COHORT)
    assert len(cases) == 8
    snapshot = json.loads((COHORT / "binding-manifest.json").read_text(encoding="utf-8"))
    assert snapshot["source_hash_format"] == "utf8_lf"
    for entry in snapshot["cases"]:
        raw = source_file(COHORT, snapshot, f"inputs/{entry['source_case']}.json").read_bytes()
        assert (
            entry["source_sha256"]
            == hashlib.sha256(raw.decode("utf-8").replace("\r\n", "\n").encode()).hexdigest()
        )
    assert snapshot["binding_semantics"] == "new_synthetic_available_materials_not_historical_usage"
    for case in cases:
        old = json.loads(
            source_file(COHORT, snapshot, f"inputs/{case.case_id}.v1.json").read_text(
                encoding="utf-8"
            )
        )
        previous = json.loads(
            (ROOT / "service_regression/inputs" / f"{case.case_id}.v2.json").read_text(
                encoding="utf-8"
            )
        )
        original = {item["ref"]: item for item in old["payload"]["evidence"]}
        source = case.payload["service_input"]
        for turn, before in zip(
            source["turns"], previous["payload"]["service_input"]["turns"], strict=True
        ):
            assert turn["question_contract"] == before["question_contract"]
            assert turn["question"] == before["question"] and turn["answer"] == before["answer"]
            for evidence in turn["evidences"]:
                raw = original[evidence["id"]]
                assert evidence["snippet"] == raw["text"] and evidence["path"] == raw["path"]
                assert f"{evidence['start_line']}-{evidence['end_line']}" == raw["lines"]
                assert evidence["usage"] == "evaluation_basis"
        assert {item["id"] for turn in source["turns"] for item in turn["evidences"]} == {
            "m1",
            "m2",
        }
        assert not any("recovery enum" in value for value in source["limitations"])
        assert any("합성 SHA" in value and "실제" in value for value in source["limitations"])
        assert case.expectation["review"]["status"] == "unreviewed"
        assert case.expectation["review"]["reviewer"] is None


def test_source_cohort_does_not_weaken_the_original_expected_behavior():
    cases = load_cases(COHORT)
    assert len(cases) == 8
    for case in cases:
        before = json.loads(
            (ROOT / "service_regression/expectations" / f"{case.case_id}.v2.json").read_text(
                encoding="utf-8"
            )
        )
        for key in ("allowed", "forbidden", "grader_controls"):
            assert case.expectation[key] == before[key]


@pytest.mark.parametrize("line_ending", ["lf", "crlf"])
def test_committed_source_provenance_survives_checkout_line_endings(line_ending):
    manifest = json.loads((COHORT / "binding-manifest.json").read_text(encoding="utf-8"))
    for entry in manifest["cases"]:
        original = source_file(COHORT, manifest, f"inputs/{entry['source_case']}.json").read_bytes()
        lf = original.decode("utf-8").replace("\r\n", "\n")
        checkout = lf if line_ending == "lf" else lf.replace("\n", "\r\n")
        assert (
            hashlib.sha256(checkout.replace("\r\n", "\n").encode()).hexdigest()
            == entry["source_sha256"]
        )
