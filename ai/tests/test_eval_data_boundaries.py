"""Eval fixture boundary checks.

docs/task-12-evaluation.md, spec/ai/decisions/0007-evaluation-design-policy.md,
spec/ai/decisions/0009-ai-evaluation-method.md

Exercises the candidate loader (eval_loader.py) against synthetic fixtures written to
tmp_path — never against ai/evals/, which stays empty until real cases are approved.
"""

import json
from pathlib import Path

import pytest
from eval_loader import FixtureError, load_cases


def _write(directory: Path, name: str, content: dict) -> None:
    directory.joinpath(f"{name}.json").write_text(json.dumps(content), encoding="utf-8")


def _input(
    case_id: str,
    version: int = 1,
    case_type: str = "qa_next_action",
    source_group: str = "group-a",
    split: str = "dev",
    payload: dict | None = None,
) -> dict:
    return {
        "case_id": case_id,
        "version": version,
        "case_type": case_type,
        "source_group": source_group,
        "split": split,
        "payload": payload if payload is not None else {"question": "why redis?"},
    }


def _expectation(case_id: str, version: int = 1) -> dict:
    return {
        "case_id": case_id,
        "version": version,
        "allowed": ["mentions cache latency"],
        "forbidden": ["invents an unrelated technology"],
    }


@pytest.fixture
def fixture_dirs(tmp_path: Path) -> tuple[Path, Path]:
    inputs_dir = tmp_path / "inputs"
    expectations_dir = tmp_path / "expectations"
    inputs_dir.mkdir()
    expectations_dir.mkdir()
    return inputs_dir, expectations_dir


def test_loads_matched_pairs_across_splits(fixture_dirs):
    inputs_dir, expectations_dir = fixture_dirs
    _write(inputs_dir, "case-1", _input("case-1", source_group="group-a", split="dev"))
    _write(expectations_dir, "case-1", _expectation("case-1"))
    _write(inputs_dir, "case-2", _input("case-2", source_group="group-b", split="holdout"))
    _write(expectations_dir, "case-2", _expectation("case-2"))

    cases = load_cases(inputs_dir, expectations_dir)

    assert {case.case_id for case in cases} == {"case-1", "case-2"}
    assert {case.split for case in cases} == {"dev", "holdout"}


def test_execution_payload_excludes_control_and_expectation_fields(fixture_dirs):
    inputs_dir, expectations_dir = fixture_dirs
    _write(inputs_dir, "case-1", _input("case-1", payload={"question": "why redis?"}))
    _write(expectations_dir, "case-1", _expectation("case-1"))

    [case] = load_cases(inputs_dir, expectations_dir)

    assert case.execution_payload == {"question": "why redis?"}
    control_fields = (
        "case_id",
        "version",
        "case_type",
        "source_group",
        "split",
        "allowed",
        "forbidden",
    )
    for control_field in control_fields:
        assert control_field not in case.execution_payload


def test_rejects_orphan_input_without_expectation(fixture_dirs):
    inputs_dir, expectations_dir = fixture_dirs
    _write(inputs_dir, "case-1", _input("case-1"))

    with pytest.raises(FixtureError, match="orphan"):
        load_cases(inputs_dir, expectations_dir)


def test_rejects_orphan_expectation_without_input(fixture_dirs):
    inputs_dir, expectations_dir = fixture_dirs
    _write(expectations_dir, "case-1", _expectation("case-1"))

    with pytest.raises(FixtureError, match="orphan"):
        load_cases(inputs_dir, expectations_dir)


def test_rejects_duplicate_case_id_and_version_on_one_side(fixture_dirs):
    inputs_dir, expectations_dir = fixture_dirs
    _write(inputs_dir, "case-1", _input("case-1"))
    _write(inputs_dir, "case-1-copy", _input("case-1"))  # same (case_id, version)
    _write(expectations_dir, "case-1", _expectation("case-1"))

    with pytest.raises(FixtureError, match="duplicate"):
        load_cases(inputs_dir, expectations_dir)


def test_rejects_mismatched_version_as_orphan(fixture_dirs):
    """A pair meant for the same case but disagreeing on version is not silently paired."""
    inputs_dir, expectations_dir = fixture_dirs
    _write(inputs_dir, "case-1", _input("case-1", version=1))
    _write(expectations_dir, "case-1", _expectation("case-1", version=2))

    with pytest.raises(FixtureError, match="orphan"):
        load_cases(inputs_dir, expectations_dir)


def test_rejects_source_group_split_leak(fixture_dirs):
    inputs_dir, expectations_dir = fixture_dirs
    _write(inputs_dir, "case-1", _input("case-1", source_group="group-a", split="dev"))
    _write(expectations_dir, "case-1", _expectation("case-1"))
    _write(inputs_dir, "case-2", _input("case-2", source_group="group-a", split="holdout"))
    _write(expectations_dir, "case-2", _expectation("case-2"))

    with pytest.raises(FixtureError, match="both dev and holdout"):
        load_cases(inputs_dir, expectations_dir)


def test_rejects_unknown_case_type(fixture_dirs):
    inputs_dir, expectations_dir = fixture_dirs
    _write(inputs_dir, "case-1", _input("case-1", case_type="not_a_real_type"))
    _write(expectations_dir, "case-1", _expectation("case-1"))

    with pytest.raises(FixtureError, match="unknown case_type"):
        load_cases(inputs_dir, expectations_dir)


def test_rejects_unknown_split(fixture_dirs):
    inputs_dir, expectations_dir = fixture_dirs
    _write(inputs_dir, "case-1", _input("case-1", split="staging"))
    _write(expectations_dir, "case-1", _expectation("case-1"))

    with pytest.raises(FixtureError, match="unknown split"):
        load_cases(inputs_dir, expectations_dir)


def test_rejects_missing_control_field(fixture_dirs):
    inputs_dir, expectations_dir = fixture_dirs
    broken = _input("case-1")
    del broken["source_group"]
    _write(inputs_dir, "case-1", broken)
    _write(expectations_dir, "case-1", _expectation("case-1"))

    with pytest.raises(FixtureError, match="missing required field"):
        load_cases(inputs_dir, expectations_dir)
