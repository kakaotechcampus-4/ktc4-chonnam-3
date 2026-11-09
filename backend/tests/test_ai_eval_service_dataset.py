"""v1 검수 원본과 새 합성 전제를 분리하고 실제 서비스 입력 계약을 검증한다."""

import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "ai/evals/service_regression"
sys.path.insert(0, str(ROOT / "ai/evals"))

from eval_cases import load_cases  # noqa: E402
from eval_runner import ExecutionError  # noqa: E402
from source_snapshot import source_file  # noqa: E402

from scripts.ai_eval_bridge import prepare  # noqa: E402


def dataset():
    assert DATASET.exists(), "explicit service-regression v2 dataset is missing"
    return load_cases(DATASET)


def test_v2_cases_bind_real_service_contracts_without_approving_new_premises():
    cases = dataset()
    assert len([case for case in cases if case.split == "dev"]) == 29
    assert len([case for case in cases if case.split == "holdout"]) == 3
    assert {prepare(case.kind, case.model_input())[0] for case in cases} == {
        "director",
        "answer_analysis",
        "report",
    }
    assert all(case.expectation["review"]["status"] == "unreviewed" for case in cases)
    assert all(case.expectation["review"]["reviewer"] is None for case in cases)


def test_binding_provenance_preserves_original_text_and_declares_added_assumptions():
    dataset()
    manifest = json.loads((DATASET / "binding-manifest.json").read_text(encoding="utf-8"))
    assert manifest["original_file_hash_format"] == "utf8_lf"
    for relative, expected in manifest["original_files"].items():
        normalized = (
            source_file(DATASET, manifest, relative).read_text(encoding="utf-8").encode("utf-8")
        )
        assert hashlib.sha256(normalized).hexdigest() == expected
    assert len(manifest["original_files"]) == 58
    bindings = manifest["bindings"]
    assert len(bindings) == 32
    assert all(item["added_premises"] for item in bindings)
    assert all(item["review_status"] == "unreviewed" for item in bindings)
    assert manifest["holdout_status"] == "public_synthetic_contract_validation_not_release_holdout"


def test_holdout_source_groups_are_new_and_cannot_relabel_the_existing_dev_sources():
    cases = dataset()
    old_groups = {
        case.source_group_id
        for case in load_cases(ROOT / "ai/evals", allow_legacy_report_contracts=True)
    }
    dev_groups = old_groups | {case.source_group_id for case in cases if case.split == "dev"}
    holdout_groups = {case.source_group_id for case in cases if case.split == "holdout"}
    assert dev_groups.isdisjoint(holdout_groups)


def test_holdout_material_versions_do_not_reuse_development_repository_identities():
    identities = {"dev": set(), "holdout": set()}
    for case in dataset():
        data = case.payload["service_input"]
        sources = data.get("context", {}).get("repositories", []) + [
            source for turn in data.get("turns", []) for source in turn["evidences"]
        ]
        identities[case.split].update((row["repository_id"], row["git_ref"]) for row in sources)
    assert identities["dev"].isdisjoint(identities["holdout"])


def test_expected_rejection_of_a_partial_analysis_without_missing_points_is_preserved():
    fixture = next(case for case in dataset() if case.case_id == "q-0004")
    raw = fixture.model_input()
    raw["service_input"]["answer_analysis"]["missing_points"] = []
    with pytest.raises(ExecutionError) as error:
        prepare(fixture.kind, raw)
    assert error.value.stage == "input"
    assert error.value.code == "contract_semantic"
