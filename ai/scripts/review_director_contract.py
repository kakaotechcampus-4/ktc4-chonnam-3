"""Review synthetic Director contract proposals; never import this from runtime code.

This checks structure and supplied Controller constraints, not natural-language quality,
actual authorization, provider behavior, or DB/WS integration. No production DTO is adopted.
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

PERSONAS = {"hr_manager", "tech_lead", "domain_lead"}
AI_ROOT = Path(__file__).resolve().parents[1]


def _object(value: Any, fields: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError("object_fields")
    return value


def _text(value: Any) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("nonblank_text_required")


def _strings(value: Any, *, nonempty: bool = False, unique: bool = True) -> list[str]:
    if not isinstance(value, list) or (nonempty and not value):
        raise ValueError("list_required")
    for item in value:
        _text(item)
    if unique and len(set(value)) != len(value):
        raise ValueError("duplicate_reference")
    return value


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_json_key")
        result[key] = value
    return result


def _invalid_constant(value: str) -> None:
    raise ValueError("nonstandard_json_constant")


def _parse(raw: str) -> Any:
    return json.loads(raw, object_pairs_hook=_unique_object, parse_constant=_invalid_constant)


def _controller(payload: Any) -> dict[str, Any]:
    data = _object(payload, {"controller", "context"})
    _object(
        data["context"],
        {
            "history",
            "answer_analysis",
            "limitations",
            "domain_category",
            "domain_frames",
        },
    )
    control = _object(
        data["controller"],
        {
            "questions_asked",
            "answers_completed",
            "question_allowed",
            "completion_allowed",
            "allowed_personas",
            "repositories",
            "evidence",
            "tool_requests",
            "tool_calls_remaining",
        },
    )
    for name in ("questions_asked", "answers_completed", "tool_calls_remaining"):
        if type(control[name]) is not int or control[name] < 0:
            raise ValueError("invalid_controller_count")
    if not 0 <= control["answers_completed"] <= control["questions_asked"] <= 9:
        raise ValueError("inconsistent_controller_turns")
    for name in ("question_allowed", "completion_allowed"):
        if type(control[name]) is not bool:
            raise ValueError("invalid_controller_flag")
    if control["completion_allowed"] and control["answers_completed"] != 9:
        raise ValueError("inconsistent_completion_permission")
    if not set(_strings(control["allowed_personas"])) <= PERSONAS:
        raise ValueError("invalid_controller_personas")
    for name in ("repositories", "evidence", "tool_requests"):
        if not isinstance(control[name], dict):
            raise ValueError("invalid_controller_references")
        for ref in control[name]:
            _text(ref)
    for sha in control["repositories"].values():
        if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha):
            raise ValueError("fixed_sha_required")
    for ref in control["evidence"].values():
        _object(ref, {"repository_id", "git_ref"})
        _source(control, ref)
    for request in control["tool_requests"].values():
        _object(request, {"tool_name", "repository_id", "git_ref", "path"})
        _text(request["tool_name"])
        _text(request["path"])
        _source(control, request)
    return control


def _source(control: dict[str, Any], ref: dict[str, Any]) -> None:
    _text(ref["repository_id"])
    _text(ref["git_ref"])
    if control["repositories"].get(ref["repository_id"]) != ref["git_ref"]:
        raise ValueError("controller_source_outside_fixed_repository")


def _candidate(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or not isinstance(value.get("next_step"), str):
        raise ValueError("action_required")
    step = value["next_step"]
    if step == "finish":
        return _object(value, {"next_step"})
    if step == "retrieve":
        _object(value, {"next_step", "tool_requests"})
        _strings(value["tool_requests"], nonempty=True)
        return value
    if step != "ask":
        raise ValueError("unknown_action")
    _object(value, {"next_step", "question"})
    question = _object(value["question"], {"persona", "text", "question_contract"})
    _text(question["persona"])
    if question["persona"] not in PERSONAS:
        raise ValueError("unknown_persona")
    _text(question["text"])
    contract = _object(
        question["question_contract"],
        {
            "purpose",
            "required_points",
            "assumptions",
            "basis_refs",
            "evaluation_scope",
        },
    )
    _text(contract["purpose"])
    _text(contract["evaluation_scope"])
    _strings(contract["assumptions"], unique=False)
    _strings(contract["basis_refs"])
    points = contract["required_points"]
    if not isinstance(points, list) or not points:
        raise ValueError("required_points_missing")
    keys = []
    for point in points:
        _object(point, {"key", "description"})
        _text(point["description"])
        keys.append(point["key"])
    _strings(keys)
    return value


def review_candidate(payload: Any, raw_output: str) -> tuple[str, str]:
    """Check one proposal without mutation/I/O; invalid fixture inputs raise ValueError."""
    control = _controller(payload)
    try:
        parsed = _parse(raw_output)
    except (ValueError, RecursionError):
        return "parse", "invalid_json"
    try:
        candidate = _candidate(parsed)
    except ValueError as exc:
        return "schema", str(exc)
    asked, answered = control["questions_asked"], control["answers_completed"]
    if candidate["next_step"] == "finish":
        if not (asked == answered == 9 and control["completion_allowed"]):
            return "semantic", "finish_not_allowed"
    elif not (control["question_allowed"] and asked == answered < 9):
        return "semantic", "question_not_allowed"
    elif candidate["next_step"] == "retrieve":
        requests = candidate["tool_requests"]
        if len(requests) > control["tool_calls_remaining"]:
            return "semantic", "tool_budget_exceeded"
        if not set(requests) <= set(control["tool_requests"]):
            return "semantic", "tool_request_not_allowed"
    else:
        question = candidate["question"]
        persona = question["persona"]
        if persona not in control["allowed_personas"] or (asked == 0 and persona != "hr_manager"):
            return "semantic", "persona_not_allowed"
        refs = question["question_contract"]["basis_refs"]
        if not set(refs) <= set(control["evidence"]):
            return "semantic", "evidence_not_allowed"
        if persona == "tech_lead" and not refs:
            return "semantic", "technical_evidence_required"
    return "valid", "checked"


def _read_cases(directory: Path, *, inputs: bool) -> dict[tuple[str, int], dict[str, Any]]:
    cases = {}
    fields = (
        {"case_id", "version", "source_group", "split", "payload"}
        if inputs
        else {
            "case_id",
            "version",
            "candidate",
            "expected_stage",
            "review_notes",
        }
    )
    for path in sorted(directory.glob("*.json")):
        data = _object(_parse(path.read_text(encoding="utf-8")), fields)
        _text(data["case_id"])
        if type(data["version"]) is not int or data["version"] < 1:
            raise ValueError("invalid_case_version")
        key = (data["case_id"], data["version"])
        if key in cases:
            raise ValueError("duplicate_case")
        if inputs:
            _text(data["source_group"])
            if data["split"] not in ("development", "holdout"):
                raise ValueError("invalid_split")
            _controller(data["payload"])
        else:
            _text(data["review_notes"])
            if data["expected_stage"] not in ("valid", "schema", "semantic"):
                raise ValueError("invalid_expected_stage")
        cases[key] = data
    return cases


def load_cases(inputs: Path, expectations: Path) -> list[dict[str, Any]]:
    """Pair synthetic cases; metadata/expectations never become execution payload."""
    incoming = _read_cases(inputs, inputs=True)
    expected = _read_cases(expectations, inputs=False)
    if not incoming or incoming.keys() != expected.keys():
        raise ValueError("empty_or_unpaired_cases")
    groups: dict[str, str] = {}
    result = []
    for key, case in incoming.items():
        group, split = case["source_group"], case["split"]
        if groups.setdefault(group, split) != split:
            raise ValueError("source_group_crosses_splits")
        result.append(
            {
                "case_id": key[0],
                "payload": case["payload"],
                "candidate": expected[key]["candidate"],
                "expected_stage": expected[key]["expected_stage"],
            }
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, default=AI_ROOT / "evals/inputs/director")
    parser.add_argument(
        "--expectations", type=Path, default=AI_ROOT / "evals/expectations/director"
    )
    args = parser.parse_args()
    try:
        cases = load_cases(args.inputs, args.expectations)
        failed = False
        for case in cases:
            stage, code = review_candidate(case["payload"], json.dumps(case["candidate"]))
            matches = stage == case["expected_stage"]
            failed |= not matches
            print(f"{'PASS' if matches else 'FAIL'}: {case['case_id']} ({stage}/{code})")
        print(f"{len(cases)} cases; LIMIT: proposal checks only; model quality and BE/WS untested.")
        return 1 if failed else 0
    except (OSError, ValueError, RecursionError):
        print(
            "FAIL: invalid or unreadable proposal fixtures (raw contents omitted).", file=sys.stderr
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
