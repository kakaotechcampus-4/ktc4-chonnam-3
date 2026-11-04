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
# Public report score keys (ADR 0010). Copied here because evals must not import the runtime.
SCORE_KEYS = {
    "project_understanding",
    "technical_reasoning",
    "problem_solving",
    "communication",
    "contribution_clarity",
    "company_job_fit",
}
# Persona quota of one 9-turn interview (ADR 0008): history count + persona_left must equal this.
PERSONA_QUOTA = {"tech_lead": 6, "domain_lead": 2, "hr_manager": 1}
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


def _history(case: Case) -> list[dict[str, Any]]:
    history = case.payload.get("history")
    turns_ok = isinstance(history, list) and all(isinstance(t, dict) for t in history)
    if not turns_ok or not history:
        raise CaseError(f"{case.case_id}: a pair case needs a non-empty payload.history list")
    for turn in history:
        if type(turn.get("turn")) is not int or not all(
            isinstance(turn.get(k), str) for k in ("persona", "question", "answer")
        ):
            raise CaseError(
                f"{case.case_id}: history needs int turn and str persona/question/answer"
            )
    return list(history)


def _check_pairs(cases: list[Case]) -> None:
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
            history = _history(case)
            frames.append(
                (
                    [{k: v for k, v in turn.items() if k != "answer"} for turn in history],
                    {k: v for k, v in case.payload.items() if k != "history"},
                )
            )
            answers.append([turn.get("answer") for turn in history])
        if frames[0] != frames[1]:
            raise CaseError(f"pair {pair_id}: questions, personas and evidence must be identical")
        if answers[0] == answers[1]:
            raise CaseError(f"pair {pair_id}: the two cases must differ in at least one answer")


def _check_persona_quota(case: Case) -> None:
    """persona_left is what remains, so past turns plus remaining must add up to the quota."""
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
        if type(remaining) is not int or done + remaining != quota:
            raise CaseError(
                f"{case.case_id}: {persona} asked {done} + left {remaining} must equal {quota}"
            )


def load_cases(root: Path) -> list[Case]:
    """Load every input/expectation pair under root, or raise CaseError."""
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
    splits: dict[str, set[str]] = {}
    for case in cases:
        splits.setdefault(case.source_group_id, set()).add(case.split)
    leaked = sorted(group for group, used in splits.items() if len(used) > 1)
    if leaked:
        raise CaseError(f"source_group_id used in both dev and holdout: {leaked}")
    for case in cases:
        _check_persona_quota(case)
    _check_pairs(cases)
    return cases
