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

_INPUT_KEYS = {"case_id", "version", "control", "payload"}
_EXPECTATION_KEYS = {"case_id", "version", "allowed", "forbidden", "grader_controls", "review"}
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


def _check_keys(name: str, data: dict[str, Any], keys: set[str]) -> None:
    extra, missing = sorted(set(data) - keys), sorted(keys - set(data))
    if extra or missing:
        raise CaseError(f"{name}: unexpected keys {extra}, missing keys {missing}")


def _load_dir(folder: Path, keys: set[str]) -> dict[str, dict[str, Any]]:
    by_stem: dict[str, dict[str, Any]] = {}
    seen: dict[tuple[str, int], str] = {}
    for path in sorted(folder.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CaseError(f"{path.name}: {exc}") from exc
        if not isinstance(data, dict):
            raise CaseError(f"{path.name}: top level must be an object")
        _check_keys(path.name, data, keys)
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


def _check_expectation(name: str, exp: dict[str, Any]) -> None:
    for key in ("allowed", "forbidden", "grader_controls"):
        if not isinstance(exp[key], list):
            raise CaseError(f"{name}: {key} must be a list")
    for item in exp["grader_controls"]:
        if not isinstance(item, dict) or not _one_of(item.get("kind"), CONTROL_KINDS):
            raise CaseError(f"{name}: grader_controls kind is not allowed")
        if not isinstance(item.get("output"), str):
            raise CaseError(f"{name}: grader_controls output must be a string")
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


def load_cases(root: Path) -> list[Case]:
    """Load every input/expectation pair under root, or raise CaseError."""
    inputs = _load_dir(root / "inputs", _INPUT_KEYS)
    expectations = _load_dir(root / "expectations", _EXPECTATION_KEYS)
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
    return cases
