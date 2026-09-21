"""Exercise the development proposal checker, not a production Director or model."""

import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

AI_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = AI_ROOT / "scripts/review_director_contract.py"
SHA = "a" * 40


def checker():
    spec = importlib.util.spec_from_file_location("director_proposal", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def payload():
    return {
        "controller": {
            "questions_asked": 1,
            "answers_completed": 1,
            "question_allowed": True,
            "completion_allowed": False,
            "allowed_personas": ["tech_lead", "domain_lead", "hr_manager"],
            "repositories": {"repo-1": SHA},
            "evidence": {"e-1": {"repository_id": "repo-1", "git_ref": SHA}},
            "tool_requests": {
                "read-main": {
                    "tool_name": "read_file",
                    "repository_id": "repo-1",
                    "git_ref": SHA,
                    "path": "src/main.py",
                }
            },
            "tool_calls_remaining": 1,
        },
        "context": {
            "history": [],
            "answer_analysis": {"limitations": ["합성 분석 결과; 전체 DTO 검증 대상 아님"]},
            "limitations": [],
            "domain_category": None,
            "domain_frames": [],
        },
    }


def question():
    return {
        "next_step": "ask",
        "question": {
            "persona": "tech_lead",
            "text": "동시 요청을 처리할 때 이 설계를 선택한 이유를 설명해 주세요.",
            "question_contract": {
                "purpose": "동시 요청 처리 방식의 선택 근거 확인",
                "required_points": [{"key": "choice", "description": "설계 선택 이유"}],
                "assumptions": [],
                "basis_refs": ["e-1"],
                "evaluation_scope": "질문한 설계 선택 이유에 한정",
            },
        },
    }


def test_checks_valid_candidate_without_mutating_input():
    request = payload()
    before = copy.deepcopy(request)
    assert checker().review_candidate(request, json.dumps(question())) == ("valid", "checked")
    assert request == before


@pytest.mark.parametrize(
    "raw",
    [
        '{"next_step":',
        '{"next_step":"ask","next_step":"finish"}',
        '{"next_step": NaN}',
        '{"next_step": Infinity}',
    ],
)
def test_rejects_unparseable_or_ambiguous_json(raw):
    assert checker().review_candidate(payload(), raw)[0] == "parse"


@pytest.mark.parametrize(
    "raw",
    [
        "[]",
        "null",
        "true",
        '{"next_step":"rewrite"}',
        '{"next_step":"finish","question":{}}',
        '{"next_step":"ask"}',
    ],
)
def test_rejects_wrong_or_mixed_action_shapes(raw):
    assert checker().review_candidate(payload(), raw)[0] == "schema"


@pytest.mark.parametrize(
    ("path", "value", "stage"),
    [
        (("question", "text"), " ", "schema"),
        (("question", "turn_no"), 2, "schema"),
        (("question", "persona"), "invented", "schema"),
        (("question", "question_contract"), None, "schema"),
        (("question", "question_contract", "required_points"), [], "schema"),
        (
            ("question", "question_contract", "required_points"),
            [{"key": "a", "description": "one"}, {"key": "a", "description": "two"}],
            "schema",
        ),
        (("question", "question_contract", "assumptions"), [None], "schema"),
        (("question", "question_contract", "basis_refs"), ["e-1", "e-1"], "schema"),
        (("question", "question_contract", "basis_refs"), ["unknown"], "semantic"),
        (("question", "question_contract", "basis_refs"), [], "semantic"),
    ],
)
def test_rejects_invalid_questions(path, value, stage):
    candidate = question()
    target = candidate
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    assert checker().review_candidate(payload(), json.dumps(candidate))[0] == stage


def test_first_question_requires_hr_but_not_code_evidence():
    request = payload()
    request["controller"].update(questions_asked=0, answers_completed=0)
    candidate = question()
    assert checker().review_candidate(request, json.dumps(candidate))[0] == "semantic"
    candidate["question"]["persona"] = "hr_manager"
    candidate["question"]["question_contract"]["basis_refs"] = []
    assert checker().review_candidate(request, json.dumps(candidate))[0] == "valid"


@pytest.mark.parametrize("persona", ["hr_manager", "domain_lead"])
def test_nontechnical_question_can_have_no_code_evidence(persona):
    candidate = question()
    candidate["question"]["persona"] = persona
    candidate["question"]["question_contract"]["basis_refs"] = []
    assert checker().review_candidate(payload(), json.dumps(candidate))[0] == "valid"


@pytest.mark.parametrize(
    "updates",
    [
        {"allowed_personas": ["hr_manager"]},
        {"answers_completed": 0},
        {"question_allowed": False},
        {"questions_asked": 9, "answers_completed": 9, "question_allowed": False},
    ],
)
def test_obeys_controller_constraints(updates):
    request = payload()
    request["controller"].update(updates)
    assert checker().review_candidate(request, json.dumps(question()))[0] == "semantic"


@pytest.mark.parametrize(
    ("asked", "answered", "allowed", "expected"),
    [
        (8, 8, False, "semantic"),
        (9, 8, False, "semantic"),
        (9, 9, False, "semantic"),
        (9, 9, True, "valid"),
    ],
)
def test_finish_requires_ninth_answer_and_controller_confirmation(
    asked, answered, allowed, expected
):
    request = payload()
    request["controller"].update(
        questions_asked=asked,
        answers_completed=answered,
        completion_allowed=allowed,
        question_allowed=False,
    )
    assert checker().review_candidate(request, '{"next_step":"finish"}')[0] == expected


@pytest.mark.parametrize(
    ("requests", "budget", "expected"),
    [
        (["read-main"], 1, "valid"),
        (["read-main"], 0, "semantic"),
        (["unknown"], 1, "semantic"),
        (["read-main", "read-main"], 2, "schema"),
        ([], 1, "schema"),
    ],
)
def test_retrieve_is_limited_to_supplied_requests_and_budget(requests, budget, expected):
    request = payload()
    request["controller"]["tool_calls_remaining"] = budget
    before = copy.deepcopy(request)
    raw = json.dumps({"next_step": "retrieve", "tool_requests": requests})
    assert checker().review_candidate(request, raw)[0] == expected
    assert request == before


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("questions_asked", True),
        ("answers_completed", 2),
        ("tool_calls_remaining", -1),
        ("repositories", {"repo-1": "main"}),
        ("evidence", {"e-1": {"repository_id": "other", "git_ref": SHA}}),
        ("evidence", {"e-1": {"repository_id": "repo-1", "git_ref": "b" * 40}}),
    ],
)
def test_incoherent_controller_fixture_is_not_blame_assigned_to_model(key, value):
    request = payload()
    request["controller"][key] = value
    with pytest.raises(ValueError):
        checker().review_candidate(request, json.dumps(question()))


def write_pair(tmp_path, name="case", case_id="director-test", version=1):
    inputs, expectations = tmp_path / "inputs", tmp_path / "expectations"
    inputs.mkdir(exist_ok=True)
    expectations.mkdir(exist_ok=True)
    incoming = {
        "case_id": case_id,
        "version": version,
        "source_group": "synthetic-one",
        "split": "development",
        "payload": payload(),
    }
    expected = {
        "case_id": case_id,
        "version": version,
        "candidate": question(),
        "expected_stage": "valid",
        "review_notes": "합성 제안; 독립 검수 전",
    }
    (inputs / f"{name}.json").write_text(json.dumps(incoming), encoding="utf-8")
    (expectations / f"{name}.json").write_text(json.dumps(expected), encoding="utf-8")
    return inputs, expectations


def test_loader_keeps_control_and_expectations_out_of_execution_payload(tmp_path):
    inputs, expectations = write_pair(tmp_path)
    case = checker().load_cases(inputs, expectations)[0]
    assert set(case["payload"]) == {"controller", "context"}
    assert case["payload"] == payload()
    assert "review_notes" not in case["payload"]


@pytest.mark.parametrize("fault", ["orphan", "version", "duplicate", "metadata", "split"])
def test_loader_rejects_invalid_case_sets(tmp_path, fault):
    inputs, expectations = write_pair(tmp_path)
    if fault == "orphan":
        (expectations / "case.json").unlink()
    elif fault == "duplicate":
        write_pair(tmp_path, name="copy")
    elif fault == "split":
        write_pair(tmp_path, name="second", case_id="director-second")
        path = inputs / "second.json"
        value = json.loads(path.read_text(encoding="utf-8"))
        value["split"] = "holdout"
        path.write_text(json.dumps(value), encoding="utf-8")
    else:
        path = inputs / "case.json"
        value = json.loads(path.read_text(encoding="utf-8"))
        if fault == "version":
            value["version"] = 2
        else:
            value["payload"]["expected_stage"] = "valid"
        path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError):
        checker().load_cases(inputs, expectations)


def test_cli_reports_mismatch_without_echoing_candidate(tmp_path):
    inputs, expectations = write_pair(tmp_path)
    path = expectations / "case.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    value["candidate"]["question"]["persona"] = "private-raw-marker"
    path.write_text(json.dumps(value), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--inputs", str(inputs), "--expectations", str(expectations)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "private-raw-marker" not in result.stdout + result.stderr


def test_checked_in_proposals_are_executable():
    result = subprocess.run(
        [sys.executable, str(SCRIPT)], cwd=AI_ROOT, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    assert "4 cases" in result.stdout
    assert "LIMIT" in result.stdout
