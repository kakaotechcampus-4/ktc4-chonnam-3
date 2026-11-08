"""조회 판단 사례의 원문·기준과 실행 범위를 별도로 보존한다."""

import hashlib
import json
from pathlib import Path

import pytest
from eval_cases import load_cases

ROOT = Path(__file__).resolve().parents[2]
COHORT = ROOT / "ai/evals/component_regression"
SOURCE = ROOT / "ai/evals/service_regression"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_verification_case_changes_only_the_explicit_service_task():
    (case,) = load_cases(COHORT)
    original = read(SOURCE / "inputs/q-0007.v2.json")
    assert (case.case_id, case.version, case.kind, case.split) == ("q-0007", 3, "question", "dev")
    assert case.payload["service_task"] == "director_verification"
    assert case.payload["service_input"] == original["payload"]["service_input"]
    assert set(case.payload) == {"service_task", "service_input"}
    assert case.source_group_id == original["control"]["source_group_id"]


def test_component_scope_does_not_relabel_or_approve_the_original_criteria():
    (case,) = load_cases(COHORT)
    original = read(SOURCE / "expectations/q-0007.v2.json")
    for key in ("allowed", "forbidden", "grader_controls"):
        assert case.expectation[key] == original[key]
    review = case.expectation["review"]
    assert review["status"] == "unreviewed"
    assert review["reviewer"] is None and review["reviewed_at"] is None
    assert any("확인형 ask" in note for note in review["pending_notes"])
    assert any("Tool" in note for note in review["pending_notes"])


def test_component_provenance_identifies_original_sources_and_unexecuted_stages():
    manifest = read(COHORT / "binding-manifest.json")
    assert manifest["source_hash_format"] == "utf8_lf"
    assert len(manifest["source_files"]) == 4
    for relative, expected in manifest["source_files"].items():
        normalized = (ROOT / relative).read_text(encoding="utf-8").encode("utf-8")
        assert hashlib.sha256(normalized).hexdigest() == expected
    (binding,) = manifest["bindings"]
    assert binding["case"] == "q-0007.v3"
    assert binding["source_case"] == "q-0007.v2"
    assert binding["execution_scope"] == "verification_decision_only"
    assert binding["tool_io_executed"] is False
    assert binding["next_director_executed"] is False
    assert binding["provider_attempts_required"] == 0
    assert binding["human_review_status"] == "deferred"
    assert binding["source_input_changed"] is False
    assert binding["grader_controls_execution"] == "not_part_of_component_execution"


@pytest.mark.parametrize("newline", [b"\n", b"\r\n"], ids=["lf", "crlf"])
def test_source_binding_is_portable_without_rewriting_original_json(tmp_path, newline):
    manifest = read(COHORT / "binding-manifest.json")
    for relative, expected in manifest["source_files"].items():
        original = (ROOT / relative).read_bytes()
        # 체크아웃 줄바꿈만 바꾼 사본에서 동일한 출처 해시를 검증한다.
        copy = tmp_path / Path(relative).name
        copy.write_bytes(original.replace(b"\r\n", b"\n").replace(b"\n", newline))
        normalized = copy.read_text(encoding="utf-8").encode("utf-8")
        assert hashlib.sha256(normalized).hexdigest() == expected
        assert read(copy) == read(ROOT / relative)
        assert (ROOT / relative).read_bytes() == original


def test_pure_component_manifest_needs_no_model_prompt_or_hidden_rubric_input():
    manifest = read(COHORT / "manifest.json")
    assert manifest["prompts"] == []
    assert manifest["limits"] == read(SOURCE / "manifest.json")["limits"]
    (case,) = load_cases(COHORT)
    visible = case.model_input()
    assert visible == case.payload
    encoded = json.dumps(visible, ensure_ascii=False)
    for secret in ("grader_controls", "reviewer", "pending_notes", "execution_scope"):
        assert secret not in encoded
