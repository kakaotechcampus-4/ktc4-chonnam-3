import json
from pathlib import Path

import pytest
from eval_cases import CaseError, load_cases


def _input(case_id="q-1", version=1, **control):
    return {
        "case_id": case_id,
        "version": version,
        "control": {
            "kind": "question",
            "split": "dev",
            "source_group_id": "sg-1",
            "synthetic": True,
            **control,
        },
        "payload": {"answer": "JWT로 로그인을 구현했습니다"},
    }


def _expectation(case_id="q-1", version=1, **review):
    return {
        "case_id": case_id,
        "version": version,
        "allowed": [{"id": "a1", "purpose": "SECRET-ALLOWED"}],
        "forbidden": [{"id": "f1", "reason": "SECRET-FORBIDDEN", "type": "repeat"}],
        "grader_controls": [{"kind": "allowed", "output": "SECRET-CONTROL"}],
        "review": {
            "status": "unreviewed",
            "author": None,
            "reviewer": None,
            "reviewed_at": None,
            "pending_notes": [],
            **review,
        },
    }


def _write(root: Path, folder: str, data: dict, name: str | None = None) -> None:
    (root / folder).mkdir(exist_ok=True)
    name = name or f"{data['case_id']}.v{data['version']}.json"
    (root / folder / name).write_text(json.dumps(data), encoding="utf-8")


def _pair(root: Path, inp=None, exp=None) -> None:
    inp, exp = inp or _input(), exp or _expectation()
    _write(root, "inputs", inp)
    _write(root, "expectations", exp)


def test_valid_pair_loads_and_model_sees_only_payload(tmp_path):
    _pair(tmp_path)
    (case,) = load_cases(tmp_path)
    assert case.model_input() == {"answer": "JWT로 로그인을 구현했습니다"}
    seen = json.dumps(case.model_input(), ensure_ascii=False)
    for leaked in ("SECRET", "sg-1", "dev", "allowed", "forbidden", "review"):
        assert leaked not in seen


def test_model_input_is_a_copy(tmp_path):
    _pair(tmp_path)
    (case,) = load_cases(tmp_path)
    case.model_input()["answer"] = "changed"
    assert case.payload["answer"] == "JWT로 로그인을 구현했습니다"


def test_orphan_input_and_orphan_expectation_rejected(tmp_path):
    _write(tmp_path, "inputs", _input())
    (tmp_path / "expectations").mkdir()
    with pytest.raises(CaseError, match="unpaired"):
        load_cases(tmp_path)
    _pair(tmp_path, _input("q-2"), _expectation("q-2"))
    (tmp_path / "inputs" / "q-1.v1.json").unlink()
    (tmp_path / "expectations" / "q-1.v1.json").unlink(missing_ok=True)
    _write(tmp_path, "expectations", _expectation("q-3"))
    with pytest.raises(CaseError, match="unpaired"):
        load_cases(tmp_path)


def test_version_mismatch_rejected(tmp_path):
    _pair(tmp_path, _input(version=1), _expectation(version=2))
    with pytest.raises(CaseError, match="unpaired"):
        load_cases(tmp_path)


def test_duplicate_case_rejected(tmp_path):
    _pair(tmp_path)
    _write(tmp_path, "inputs", _input(), name="q-1.v1-copy.json")
    with pytest.raises(CaseError, match="duplicate"):
        load_cases(tmp_path)


def test_file_name_must_match_content(tmp_path):
    _write(tmp_path, "inputs", _input(), name="other.v1.json")
    _write(tmp_path, "expectations", _expectation(), name="other.v1.json")
    with pytest.raises(CaseError, match="file name"):
        load_cases(tmp_path)


def test_source_group_in_dev_and_holdout_rejected(tmp_path):
    _pair(tmp_path, _input("q-1"), _expectation("q-1"))
    _pair(tmp_path, _input("q-2", split="holdout"), _expectation("q-2"))
    with pytest.raises(CaseError, match="both dev and holdout"):
        load_cases(tmp_path)


def test_same_source_group_in_one_split_is_fine(tmp_path):
    _pair(tmp_path, _input("q-1"), _expectation("q-1"))
    _pair(tmp_path, _input("q-2"), _expectation("q-2"))
    assert len(load_cases(tmp_path)) == 2


def test_expectation_fields_in_input_rejected(tmp_path):
    leaky = _input()
    leaky["allowed"] = []
    _pair(tmp_path, leaky)
    with pytest.raises(CaseError, match="unexpected keys"):
        load_cases(tmp_path)


def test_non_synthetic_rejected(tmp_path):
    _pair(tmp_path, _input(synthetic=False))
    with pytest.raises(CaseError, match="synthetic"):
        load_cases(tmp_path)


@pytest.mark.parametrize(
    "review",
    [
        {"status": "approved"},
        {"status": "approved", "author": "a", "reviewer": "a", "reviewed_at": "2026-11-01"},
        {"status": "approved", "author": "a", "reviewer": "b"},
        {"status": "done"},
    ],
)
def test_review_cannot_be_faked(tmp_path, review):
    _pair(tmp_path, exp=_expectation(**review))
    with pytest.raises(CaseError):
        load_cases(tmp_path)


def test_approved_by_other_person_with_date_loads(tmp_path):
    review = {"status": "approved", "author": "a", "reviewer": "b", "reviewed_at": "2026-11-01"}
    _pair(tmp_path, exp=_expectation(**review))
    assert load_cases(tmp_path)[0].expectation["review"]["status"] == "approved"


def test_grader_control_output_must_be_a_string(tmp_path):
    exp = _expectation()
    exp["grader_controls"] = [{"kind": "allowed"}]
    _pair(tmp_path, exp=exp)
    with pytest.raises(CaseError, match="output"):
        load_cases(tmp_path)


@pytest.mark.parametrize("bad", [["dev"], {"a": 1}, 3, None])
def test_non_string_enum_values_raise_case_error_not_type_error(tmp_path, bad):
    _pair(tmp_path, _input(kind=bad))
    with pytest.raises(CaseError):
        load_cases(tmp_path)


@pytest.mark.parametrize("field", ["kind", "status"])
def test_non_string_control_and_review_values_raise_case_error(tmp_path, field):
    exp = _expectation()
    if field == "kind":
        exp["grader_controls"] = [{"kind": ["allowed"], "output": "x"}]
    else:
        exp["review"]["status"] = ["approved"]
    _pair(tmp_path, exp=exp)
    with pytest.raises(CaseError):
        load_cases(tmp_path)


@pytest.mark.parametrize(
    "review",
    [
        {"status": "approved", "author": 1, "reviewer": 2, "reviewed_at": 3},
        {"status": "approved", "author": "a", "reviewer": "b", "reviewed_at": True},
        {
            "status": "approved",
            "author": "a",
            "reviewer": "b",
            "reviewed_at": "2026-11-01",
            "pending_notes": ["still open"],
        },
        {"status": "pending", "pending_notes": "not a list"},
    ],
)
def test_approved_needs_strings_and_no_open_notes(tmp_path, review):
    _pair(tmp_path, exp=_expectation(**review))
    with pytest.raises(CaseError):
        load_cases(tmp_path)


@pytest.mark.parametrize(
    "review",
    [
        {"author": "gdh0730", "reviewer": "GDH0730"},
        {"author": "gdh0730", "reviewer": " gdh0730 "},
        {"author": "a", "reviewer": "   "},
        {"author": "   ", "reviewer": "b"},
        {"author": "a", "reviewer": "b", "reviewed_at": "  "},
    ],
)
def test_approved_rejects_same_account_and_blank_names(tmp_path, review):
    base = {"status": "approved", "reviewed_at": "2026-11-01"}
    _pair(tmp_path, exp=_expectation(**{**base, **review}))
    with pytest.raises(CaseError):
        load_cases(tmp_path)


@pytest.mark.parametrize("folder", ["inputs", "expectations"])
def test_invalid_utf8_raises_case_error(tmp_path, folder):
    _pair(tmp_path)
    (tmp_path / folder / "q-1.v1.json").write_bytes(b'{"case_id": "\xff"}')
    with pytest.raises(CaseError, match="q-1.v1.json"):
        load_cases(tmp_path)
