"""Candidate loader for the local synthetic eval fixture contract.

docs/task-12-evaluation.md, spec/ai/decisions/0007-evaluation-design-policy.md,
spec/ai/decisions/0009-ai-evaluation-method.md

This is a *candidate* loader only (task-12: "향후 후보 로컬 loader·harness"). It is not
part of the `devon_ai` package (ai/src) and ships nowhere; it exists to validate the
local JSON fixture contract described in ADR 0009 before any real fixtures are added
to ai/evals/. Production schema, storage, and distribution format remain undecided.

Fixture contract (ADR 0009):

- One input JSON + one expectation JSON make a case, paired by (case_id, version).
- Input JSON: {"case_id", "version", "case_type", "source_group", "split", "payload"}.
  Only "payload" may ever reach a model — everything else is loader control metadata.
- Expectation JSON: {"case_id", "version", "allowed", "forbidden", ...}. Never sent to
  a model; kept isolated from prompt/retrieval/tool input.
- Loader rejects: orphans (only one side present), duplicates (same key twice on one
  side), and cross-split leaks (same source_group used in both "dev" and "holdout").
  A content mismatch between an intended pair surfaces as an orphan or duplicate,
  since pairing is by (case_id, version) content, not by filename.

Out of scope for this first pass (left for when the underlying decision lands):
independent-reviewer / `pending` adjudication workflow (AI-L19), grader false-accept/
false-reject control checks (needs a grader), holdout-usage regression reclassification
(needs real usage tracking).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

CaseType = Literal["source_evidence", "qa_next_action", "interview_flow", "report"]
Split = Literal["dev", "holdout"]

CASE_TYPES: frozenset[str] = frozenset(
    {"source_evidence", "qa_next_action", "interview_flow", "report"}
)
SPLITS: frozenset[str] = frozenset({"dev", "holdout"})

_CONTROL_FIELDS = frozenset({"case_id", "version", "case_type", "source_group", "split"})
_REQUIRED_INPUT_FIELDS = _CONTROL_FIELDS | {"payload"}
_REQUIRED_EXPECTATION_FIELDS = frozenset({"case_id", "version", "allowed", "forbidden"})


class FixtureError(Exception):
    """The local input/expectation fixture set violates the ADR 0009 contract."""


@dataclass(frozen=True)
class EvalCase:
    case_id: str
    version: int
    case_type: CaseType
    source_group: str
    split: Split
    payload: dict[str, Any]
    expectation: dict[str, Any]

    @property
    def execution_payload(self) -> dict[str, Any]:
        """The only data a model may receive — no control or expectation fields."""
        return self.payload


_CaseKey = tuple[str, int]


def load_cases(inputs_dir: Path, expectations_dir: Path) -> list[EvalCase]:
    """Load and pair every *.json fixture under the two directories.

    Raises FixtureError on any orphan, duplicate, missing required field, unknown
    case_type/split, or source_group split leak.
    """
    inputs = _load_side(inputs_dir, _REQUIRED_INPUT_FIELDS)
    expectations = _load_side(expectations_dir, _REQUIRED_EXPECTATION_FIELDS)

    orphan_inputs = sorted(inputs.keys() - expectations.keys())
    orphan_expectations = sorted(expectations.keys() - inputs.keys())
    if orphan_inputs or orphan_expectations:
        raise FixtureError(
            "orphan fixture pair(s): "
            f"inputs without expectations={orphan_inputs}, "
            f"expectations without inputs={orphan_expectations}"
        )

    cases = [_build_case(inputs[key], expectations[key]) for key in sorted(inputs)]
    _check_split_leak(cases)
    return cases


def _load_side(directory: Path, required_fields: frozenset[str]) -> dict[_CaseKey, dict[str, Any]]:
    seen: dict[_CaseKey, dict[str, Any]] = {}
    for path in sorted(directory.glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        missing = required_fields - raw.keys()
        if missing:
            raise FixtureError(f"{path}: missing required field(s) {sorted(missing)}")

        key = (raw["case_id"], raw["version"])
        if key in seen:
            raise FixtureError(f"duplicate fixture for case {key} in {directory}")
        seen[key] = raw
    return seen


def _build_case(raw_input: dict[str, Any], raw_expectation: dict[str, Any]) -> EvalCase:
    case_type = raw_input["case_type"]
    if case_type not in CASE_TYPES:
        raise FixtureError(
            f"unknown case_type {case_type!r} (expected one of {sorted(CASE_TYPES)})"
        )

    split = raw_input["split"]
    if split not in SPLITS:
        raise FixtureError(f"unknown split {split!r} (expected one of {sorted(SPLITS)})")

    return EvalCase(
        case_id=raw_input["case_id"],
        version=raw_input["version"],
        case_type=case_type,
        source_group=raw_input["source_group"],
        split=split,
        payload=raw_input["payload"],
        expectation=raw_expectation,
    )


def _check_split_leak(cases: list[EvalCase]) -> None:
    splits_by_group: dict[str, set[Split]] = {}
    for case in cases:
        splits_by_group.setdefault(case.source_group, set()).add(case.split)

    leaked = {group: sorted(splits) for group, splits in splits_by_group.items() if len(splits) > 1}
    if leaked:
        raise FixtureError(f"source_group used in both dev and holdout: {leaked}")
