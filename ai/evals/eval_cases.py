"""Local synthetic eval case loader. Not part of the runtime package.

Format and rules: ai/evals/README.md, ADR 0007 and 0009.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

KINDS = {"evidence", "question", "flow", "report"}
SPLITS = {"dev", "holdout"}
CONTROL_KINDS = {"allowed", "forbidden", "ambiguous", "invalid_ref", "tool_failure"}
REVIEW_STATUSES = {"unreviewed", "approved", "pending", "invalid"}
PERSONA_QUOTA = {"tech_lead": 6, "domain_lead": 2, "hr_manager": 1}
# Public report score keys (ADR 0010). Copied here because evals must not import the runtime.
SCORE_KEYS = {
    "project_understanding",
    "technical_reasoning",
    "problem_solving",
    "communication",
    "contribution_clarity",
    "company_job_fit",
}
PAIR_ROLES = {"stronger", "weaker"}
_PAIR_KEYS = {"pair_id", "role", "key", "min_gap"}

_INPUT_KEYS = {"case_id", "version", "control", "payload"}
_EXPECTATION_KEYS = {"case_id", "version", "allowed", "forbidden", "grader_controls", "review"}
_EXPECTATION_OPTIONAL = frozenset(
    {"source_fact", "pair"}
)  # source_fact: fact-table id the case was modeled on; pair: report score order pair
_CONTROL_KEYS = {"kind", "split", "source_group_id", "synthetic"}
_REVIEW_KEYS = {"status", "author", "reviewer", "reviewed_at", "pending_notes"}


class CaseError(ValueError):
    """A case file or pair breaks the fixture contract."""


@dataclass(frozen=True)
class Case:
    case_id: str
    version: int
    kind: str
    split: str
    source_group_id: str
    payload: dict[str, Any]
    expectation: dict[str, Any]

    def model_input(self) -> dict[str, Any]:
        """The only part a model may receive."""
        return copy.deepcopy(self.payload)


def _check_keys(
    name: str, data: dict[str, Any], keys: set[str], optional: frozenset[str] = frozenset()
) -> None:
    extra, missing = sorted(set(data) - keys - optional), sorted(keys - set(data))
    if extra or missing:
        raise CaseError(f"{name}: unexpected keys {extra}, missing keys {missing}")


def _load_dir(
    folder: Path, keys: set[str], optional: frozenset[str] = frozenset()
) -> dict[str, dict[str, Any]]:
    by_stem: dict[str, dict[str, Any]] = {}
    seen: dict[tuple[str, int], str] = {}
    for path in sorted(folder.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CaseError(f"{path.name}: {exc}") from exc
        if not isinstance(data, dict):
            raise CaseError(f"{path.name}: top level must be an object")
        _check_keys(path.name, data, keys, optional)
        case_id, version = data["case_id"], data["version"]
        if not isinstance(case_id, str) or type(version) is not int:
            raise CaseError(f"{path.name}: case_id must be a string and version an integer")
        if (case_id, version) in seen:
            first = seen[(case_id, version)]
            raise CaseError(f"duplicate case {case_id} v{version}: {first}, {path.name}")
        seen[(case_id, version)] = path.name
        by_stem[path.stem] = data
    for stem, data in by_stem.items():  # after the duplicate scan, so order cannot hide a copy
        if stem != f"{data['case_id']}.v{data['version']}":
            raise CaseError(
                f"{stem}.json: file name must be {data['case_id']}.v{data['version']}.json"
            )
    return by_stem


def _one_of(value: Any, allowed: set[str]) -> bool:
    return isinstance(value, str) and value in allowed  # a list or dict must not reach the set


def _check_control(name: str, control: Any) -> None:
    if not isinstance(control, dict):
        raise CaseError(f"{name}: control must be an object")
    _check_keys(f"{name} control", control, _CONTROL_KEYS)
    if not _one_of(control["kind"], KINDS) or not _one_of(control["split"], SPLITS):
        raise CaseError(f"{name}: control kind or split is not allowed")
    if not isinstance(control["source_group_id"], str) or not control["source_group_id"]:
        raise CaseError(f"{name}: source_group_id must be a non-empty string")
    if control["synthetic"] is not True:
        raise CaseError(f"{name}: only synthetic cases may live here")


def _check_pair_field(name: str, pair: Any) -> None:
    if not isinstance(pair, dict):
        raise CaseError(f"{name}: pair must be an object")
    _check_keys(f"{name} pair", pair, _PAIR_KEYS)
    if not isinstance(pair["pair_id"], str) or not pair["pair_id"]:
        raise CaseError(f"{name}: pair_id must be a non-empty string")
    if not _one_of(pair["role"], PAIR_ROLES) or not _one_of(pair["key"], SCORE_KEYS):
        raise CaseError(f"{name}: pair role or key is not allowed")
    gap = pair["min_gap"]
    if type(gap) is not int or not 1 <= gap <= 100:  # bool is an int subclass, so check type
        raise CaseError(f"{name}: pair min_gap must be an integer from 1 to 100")


def _check_expectation(name: str, exp: dict[str, Any]) -> None:
    for key in ("allowed", "forbidden", "grader_controls"):
        if not isinstance(exp[key], list):
            raise CaseError(f"{name}: {key} must be a list")
    for item in exp["grader_controls"]:
        if not isinstance(item, dict) or not _one_of(item.get("kind"), CONTROL_KINDS):
            raise CaseError(f"{name}: grader_controls kind is not allowed")
        if not isinstance(item.get("output"), str):
            raise CaseError(f"{name}: grader_controls output must be a string")
    fact = exp.get("source_fact", "x")
    if not isinstance(fact, str) or not fact:
        raise CaseError(f"{name}: source_fact must be a non-empty string")
    if "pair" in exp:
        _check_pair_field(name, exp["pair"])
    review = exp["review"]
    if not isinstance(review, dict):
        raise CaseError(f"{name}: review must be an object")
    _check_keys(f"{name} review", review, _REVIEW_KEYS)
    if not _one_of(review["status"], REVIEW_STATUSES):
        raise CaseError(f"{name}: review status is not allowed")
    if not isinstance(review["pending_notes"], list):
        raise CaseError(f"{name}: pending_notes must be a list")
    if review["status"] == "approved":
        names = [review[k] for k in ("author", "reviewer", "reviewed_at")]
        if not all(isinstance(v, str) and v.strip() for v in names):
            raise CaseError(f"{name}: approved needs an author, a reviewer and a date")
        author, reviewer = (v.strip().casefold() for v in names[:2])  # GitHub logins ignore case
        if author == reviewer:
            raise CaseError(f"{name}: approved needs a reviewer other than the author")
        if review["pending_notes"]:
            raise CaseError(f"{name}: approved cannot have open pending_notes")


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _check_contract(case_id: str, contract: Any) -> None:
    """Question Contract subset a report payload carries (ai/evals/README.md)."""
    keys = ("purpose", "required_points", "evaluation_scope")
    points: Any = contract.get("required_points") if isinstance(contract, dict) else None
    optional = {"assumptions", "basis_refs", "evaluation_keys"}
    ok = isinstance(contract, dict) and set(keys) <= set(contract) <= set(keys) | optional
    ok = ok and _text(contract["purpose"]) and _text(contract["evaluation_scope"])
    ok = ok and isinstance(points, list) and bool(points)
    ok = ok and all(
        isinstance(p, dict) and set(p) == {"key", "description"} and all(map(_text, p.values()))
        for p in points
    )
    if not ok or len({p["key"] for p in points}) != len(points):
        raise CaseError(f"{case_id}: history turn needs a valid question_contract")


TOOL_STATUSES = {"found", "not_found", "insufficient_analysis", "tool_error"}


def _check_links(case: Case, history: list[dict[str, Any]]) -> None:
    """Optional turn evidence_refs and payload tool_results must point at real refs and turns."""
    name = case.case_id
    evidence = case.payload.get("evidence", [])
    refs = {item.get("ref") for item in evidence if isinstance(item, dict)}
    for turn in history:
        linked = turn.get("evidence_refs", [])
        if (
            not isinstance(linked, list)
            or len(set(map(str, linked))) != len(linked)
            or not all(isinstance(ref, str) and ref in refs for ref in linked)
        ):
            raise CaseError(f"{name}: evidence_refs must name registered evidence refs once each")
    numbers = {turn["turn"] for turn in history}
    results = case.payload.get("tool_results", [])
    if not isinstance(results, list):
        raise CaseError(f"{name}: tool_results must be a list")
    for item in results:
        keys = {"turn", "status", "limitations", "error_code"}
        if not isinstance(item, dict) or set(item) != keys:
            raise CaseError(f"{name}: tool_results item needs {sorted(keys)}")
        limits, code = item["limitations"], item["error_code"]
        ok = type(item["turn"]) is int and item["turn"] in numbers
        ok = ok and _one_of(item["status"], TOOL_STATUSES)
        ok = ok and isinstance(limits, list) and all(_text(text) for text in limits)
        ok = ok and (code is None or _text(code))
        if ok and item["status"] == "tool_error":
            ok = code is not None and bool(limits)
        if ok and item["status"] == "insufficient_analysis":
            ok = code is None and bool(limits)
        if ok and item["status"] in ("found", "not_found"):
            ok = code is None
        if not ok:
            raise CaseError(f"{name}: tool_results item is not a valid ToolResult for a turn")


def _history(case: Case, *, allow_legacy_report_contracts: bool = False) -> list[dict[str, Any]]:
    history = case.payload.get("history")
    explicit = case.payload.get("service_task") == "report"
    if explicit:
        service = case.payload.get("service_input")
        turns = service.get("turns") if isinstance(service, dict) else None
        if not isinstance(turns, list) or not all(isinstance(turn, dict) for turn in turns):
            raise CaseError(f"{case.case_id}: runtime report needs service_input.turns")
        history = [
            {
                "turn": turn.get("turn_no"),
                "persona": turn.get("persona"),
                "question": turn.get("question"),
                "answer": turn.get("answer"),
                "question_contract": turn.get("question_contract"),
                **(
                    {"follows": turn["parent_turn_no"]}
                    if turn.get("parent_turn_no") is not None
                    else {}
                ),
            }
            for turn in turns
        ]
    turns_ok = isinstance(history, list) and all(isinstance(t, dict) for t in history)
    if not turns_ok or not history:
        raise CaseError(f"{case.case_id}: a report case needs a non-empty payload.history list")
    for turn in history:
        if (
            type(turn.get("turn")) is not int
            or not all(isinstance(turn.get(k), str) for k in ("persona", "question"))
            or not (isinstance(turn.get("answer"), str) or explicit and turn.get("answer") is None)
        ):
            raise CaseError(
                f"{case.case_id}: history needs int turn and str persona/question/answer"
            )
    numbers = [turn["turn"] for turn in history]
    if len(set(numbers)) != len(numbers):
        raise CaseError(f"{case.case_id}: history turn numbers must be unique, got {numbers}")
    # 축약 v1의 검수만 명시적으로 허용한다. 서비스 입력·부분 계약은 계속 엄격히 검사한다.
    contracts_required = (
        explicit
        or not allow_legacy_report_contracts
        or any("question_contract" in turn for turn in history)
    )
    for turn in history:
        if contracts_required:
            _check_contract(case.case_id, turn.get("question_contract"))
        follows = turn.get("follows")
        if "follows" in turn and (
            type(follows) is not int or follows not in numbers or follows >= turn["turn"]
        ):
            raise CaseError(f"{case.case_id}: follows must name an earlier turn")
    _check_links(case, history)
    return list(history)


def _report_frame(case: Case) -> dict[str, Any]:
    """쌍 비교에서 답변만 제외하고 원문·rubric·계약을 모두 보존한다."""
    frame = copy.deepcopy(case.payload)
    turns = (
        frame["service_input"]["turns"]
        if frame.get("service_task") == "report"
        else frame["history"]
    )
    for turn in turns:
        turn.pop("answer", None)
    return frame


def _check_pairs(cases: list[Case], *, allow_legacy_report_contracts: bool = False) -> None:
    """A pair is two report cases that differ only in answers, so only answers can move a score."""
    groups: dict[str, list[Case]] = {}
    for case in cases:
        if "pair" in case.expectation:
            groups.setdefault(case.expectation["pair"]["pair_id"], []).append(case)
    for pair_id, members in sorted(groups.items()):
        roles = sorted(c.expectation["pair"]["role"] for c in members)
        if roles != ["stronger", "weaker"]:
            raise CaseError(f"pair {pair_id}: needs one stronger and one weaker case, got {roles}")
        first, second = members
        if first.kind != "report" or second.kind != "report":
            raise CaseError(f"pair {pair_id}: only report cases can be paired")
        if (first.split, first.source_group_id) != (second.split, second.source_group_id):
            raise CaseError(f"pair {pair_id}: both cases must share split and source_group_id")
        for field in ("key", "min_gap"):
            if first.expectation["pair"][field] != second.expectation["pair"][field]:
                raise CaseError(f"pair {pair_id}: both cases must use the same {field}")
        frames, answers = [], []
        for case in (first, second):
            history = _history(case, allow_legacy_report_contracts=allow_legacy_report_contracts)
            frames.append(_report_frame(case))
            answers.append([turn.get("answer") for turn in history])
        if frames[0] != frames[1]:
            raise CaseError(f"pair {pair_id}: questions, personas and evidence must be identical")
        if answers[0] == answers[1]:
            raise CaseError(f"pair {pair_id}: the two cases must differ in at least one answer")


def _check_persona_quota(case: Case) -> None:
    """진행한 질문과 남은 할당이 6·2·1을 충족하며 음수가 없는지 검사한다."""
    left, history = case.payload.get("persona_left"), case.payload.get("history")
    if left is None:
        return
    if not isinstance(left, dict) or not isinstance(history, list):
        raise CaseError(f"{case.case_id}: persona_left needs a dict and a history list")
    for persona in left:
        if persona not in PERSONA_QUOTA:
            raise CaseError(f"{case.case_id}: unknown persona in persona_left: {persona}")
    for persona, quota in PERSONA_QUOTA.items():
        done = sum(1 for t in history if isinstance(t, dict) and t.get("persona") == persona)
        remaining = left.get(persona, 0)
        if type(remaining) is not int or remaining < 0 or done + remaining != quota:
            raise CaseError(
                f"{case.case_id}: {persona} asked {done} + left {remaining} must equal {quota}"
            )


def load_cases(root: Path, *, allow_legacy_report_contracts: bool = False) -> list[Case]:
    """Load every input/expectation pair under root, or raise CaseError."""
    from source_snapshot import is_historical_snapshot, validate_bound_sources

    if is_historical_snapshot(root):
        raise CaseError("Historical source snapshot cannot be used as current evaluation cases")
    validate_bound_sources(root)
    inputs = _load_dir(root / "inputs", _INPUT_KEYS)
    expectations = _load_dir(root / "expectations", _EXPECTATION_KEYS, _EXPECTATION_OPTIONAL)
    orphans = sorted(set(inputs) ^ set(expectations))
    if orphans:
        raise CaseError(f"unpaired or mismatched id/version: {orphans}")
    cases = []
    for stem, inp in sorted(inputs.items()):
        _check_control(stem, inp["control"])
        if not isinstance(inp["payload"], dict):
            raise CaseError(f"{stem}: payload must be an object")
        _check_expectation(stem, expectations[stem])
        control = inp["control"]
        cases.append(
            Case(
                inp["case_id"],
                inp["version"],
                control["kind"],
                control["split"],
                control["source_group_id"],
                inp["payload"],
                expectations[stem],
            )
        )
    for case in cases:
        if case.kind == "report":
            _history(case, allow_legacy_report_contracts=allow_legacy_report_contracts)
        _check_persona_quota(case)
    splits: dict[str, set[str]] = {}
    for case in cases:
        splits.setdefault(case.source_group_id, set()).add(case.split)
    leaked = sorted(group for group, used in splits.items() if len(used) > 1)
    if leaked:
        raise CaseError(f"source_group_id used in both dev and holdout: {leaked}")
    _check_pairs(cases, allow_legacy_report_contracts=allow_legacy_report_contracts)
    return cases
