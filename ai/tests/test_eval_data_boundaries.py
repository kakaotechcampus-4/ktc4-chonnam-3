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


def _report_input(case_id, answer, kind="report", source_group="sg-1", question="왜 Redis인가요?"):
    inp = _input(case_id, kind=kind, source_group_id=source_group)
    inp["payload"] = {
        "history": [{"turn": 1, "persona": "tech_lead", "question": question, "answer": answer}],
        "evidence": [],
    }
    return inp


def _report_exp(case_id, role="stronger", **pair):
    exp = _expectation(case_id)
    exp["pair"] = {
        "pair_id": "rp-1",
        "role": role,
        "key": "technical_reasoning",
        "min_gap": 10,
        **pair,
    }
    return exp


def _write_report_pair(root, strong=None, weak=None, strong_exp=None, weak_exp=None):
    _pair(
        root,
        strong or _report_input("r-1", "대안을 비교했습니다"),
        strong_exp or _report_exp("r-1"),
    )
    _pair(
        root,
        weak or _report_input("r-2", "많이 써서요"),
        weak_exp or _report_exp("r-2", "weaker"),
    )


def test_valid_report_pair_loads_and_pair_stays_out_of_model_input(tmp_path):
    _write_report_pair(tmp_path)
    cases = load_cases(tmp_path)
    assert {c.expectation["pair"]["role"] for c in cases} == {"stronger", "weaker"}
    assert "rp-1" not in json.dumps([c.model_input() for c in cases])


def test_pair_needs_both_roles(tmp_path):
    _pair(tmp_path, _report_input("r-1", "a"), _report_exp("r-1"))
    with pytest.raises(CaseError, match="one stronger and one weaker"):
        load_cases(tmp_path)


def test_pair_cases_must_share_questions_and_evidence(tmp_path):
    _write_report_pair(tmp_path, weak=_report_input("r-2", "많이 써서요", question="다른 질문"))
    with pytest.raises(CaseError, match="identical"):
        load_cases(tmp_path)


def test_pair_cases_must_differ_in_an_answer(tmp_path):
    _write_report_pair(tmp_path, weak=_report_input("r-2", "대안을 비교했습니다"))
    with pytest.raises(CaseError, match="differ in at least one answer"):
        load_cases(tmp_path)


def test_pair_cases_must_share_source_group(tmp_path):
    _write_report_pair(tmp_path, weak=_report_input("r-2", "많이 써서요", source_group="sg-2"))
    with pytest.raises(CaseError, match="source_group_id"):
        load_cases(tmp_path)


def test_only_report_cases_can_be_paired(tmp_path):
    _write_report_pair(tmp_path, weak=_report_input("r-2", "많이 써서요", kind="question"))
    with pytest.raises(CaseError, match="only report"):
        load_cases(tmp_path)


def test_pair_cases_must_agree_on_key_and_min_gap(tmp_path):
    _write_report_pair(tmp_path, weak_exp=_report_exp("r-2", "weaker", min_gap=20))
    with pytest.raises(CaseError, match="same min_gap"):
        load_cases(tmp_path)


@pytest.mark.parametrize(
    "bad",
    [
        {"key": "totalScore"},
        {"role": "better"},
        {"min_gap": 0},
        {"min_gap": True},
        {"min_gap": 10.5},
        {"pair_id": ""},
    ],
)
def test_bad_pair_fields_raise_case_error(tmp_path, bad):
    _write_report_pair(tmp_path, strong_exp=_report_exp("r-1", **bad))
    with pytest.raises(CaseError):
        load_cases(tmp_path)


@pytest.mark.parametrize("folder", ["inputs", "expectations"])
def test_invalid_utf8_raises_case_error(tmp_path, folder):
    _pair(tmp_path)
    (tmp_path / folder / "q-1.v1.json").write_bytes(b'{"case_id": "\xff"}')
    with pytest.raises(CaseError, match="q-1.v1.json"):
        load_cases(tmp_path)


def test_pair_without_history_is_rejected(tmp_path):
    strong = _report_input("r-1", "a")
    strong["payload"] = {"answer": "no history"}
    _write_report_pair(tmp_path, strong=strong)
    with pytest.raises(CaseError, match="history"):
        load_cases(tmp_path)


@pytest.mark.parametrize("missing", ["turn", "persona", "question", "answer"])
def test_pair_history_turn_needs_all_fields(tmp_path, missing):
    strong = _report_input("r-1", "대안을 비교했습니다")
    del strong["payload"]["history"][0][missing]
    _write_report_pair(tmp_path, strong=strong)
    with pytest.raises(CaseError, match="history needs"):
        load_cases(tmp_path)


def test_pair_history_turn_numbers_must_be_unique(tmp_path):
    cases = []
    for case_id, answer in (("r-1", "대안을 비교했습니다"), ("r-2", "많이 써서요")):
        inp = _report_input(case_id, answer)
        turn = inp["payload"]["history"][0]
        inp["payload"]["history"] = [turn, {**turn, "answer": "다른 답"}]  # 둘 다 turn 1
        cases.append(inp)
    _write_report_pair(tmp_path, *cases)
    with pytest.raises(CaseError, match="unique"):
        load_cases(tmp_path)


def test_negative_persona_left_is_rejected_even_when_the_sum_matches(tmp_path):
    history = ["tech_lead"] * 7 + ["hr_manager"]  # 기술 질문이 정원 6을 넘은 이력
    left = {"tech_lead": -1, "domain_lead": 2, "hr_manager": 0}
    _pair(tmp_path, _quota_case(history, left))
    with pytest.raises(CaseError, match="tech_lead"):
        load_cases(tmp_path)


def _quota_case(history, left):
    inp = _input()
    turns = enumerate(history, 1)
    inp["payload"] = {
        "history": [{"turn": n, "persona": p, "question": "q", "answer": "a"} for n, p in turns],
        "persona_left": left,
    }
    return inp


def test_persona_left_must_complete_the_interview_quota(tmp_path):
    _pair(tmp_path, _quota_case(["hr_manager", "tech_lead"], {"tech_lead": 5, "domain_lead": 2}))
    assert load_cases(tmp_path)


@pytest.mark.parametrize(
    "left",
    [
        {"tech_lead": 4, "domain_lead": 2},
        {"tech_lead": 5},
        {"tech_lead": 5, "domain_lead": 2, "x": 1},
    ],
    ids=["tech short", "domain missing", "unknown persona"],
)
def test_persona_left_that_breaks_the_quota_is_rejected(tmp_path, left):
    _pair(tmp_path, _quota_case(["hr_manager", "tech_lead"], left))
    with pytest.raises(CaseError):
        load_cases(tmp_path)
