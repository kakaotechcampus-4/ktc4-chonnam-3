"""Checks a grader against reviewed control outputs. Not part of the runtime package.

ADR 0009: a grader is tried on allowed, forbidden, ambiguous, invalid-reference and
tool-failure controls, and false accepts and false rejects are counted per control kind.
Cases that are not approved stay in the totals but out of the quality denominator.
"""

from __future__ import annotations

import copy
from collections import Counter
from collections.abc import Callable, Sequence
from typing import Any

from eval_cases import CONTROL_KINDS, Case

# Candidate expectation for each control kind (author assumption, pending team review).
EXPECTED = {
    "allowed": "accept",
    "forbidden": "reject",
    "invalid_ref": "reject",
    "tool_failure": "reject",
    "ambiguous": "ambiguous",
}
VERDICTS = set(EXPECTED.values())
_WRONG = {"accept": "false_accept", "reject": "false_reject", "ambiguous": "abstained"}
OUTCOMES = ("correct", "false_accept", "false_reject", "abstained", "error")

# The grader sees the rubric (allowed, forbidden) and one output, never the control kind.
Grader = Callable[[dict[str, Any], str], str]


def check_grader(cases: Sequence[Case], grader: Grader) -> dict[str, Any]:
    by_kind = {kind: Counter[str]() for kind in sorted(CONTROL_KINDS)}
    excluded: Counter[str] = Counter()
    evaluated = 0
    for case in cases:
        status = case.expectation["review"]["status"]
        if status != "approved":
            excluded[status] += 1
            continue
        if not case.expectation["grader_controls"]:
            excluded["no_controls"] += 1  # nothing to check, so it is not a graded case
            continue
        evaluated += 1
        rubric = {k: case.expectation[k] for k in ("allowed", "forbidden")}
        for control in case.expectation["grader_controls"]:
            try:
                got = grader(copy.deepcopy(rubric), control["output"])
            except Exception:  # a crashing grader is a result, not a skipped case
                by_kind[control["kind"]]["error"] += 1
                continue
            if got not in VERDICTS:
                raise ValueError(f"grader returned {got!r}, expected one of {sorted(VERDICTS)}")
            outcome = "correct" if got == EXPECTED[control["kind"]] else _WRONG[got]
            by_kind[control["kind"]][outcome] += 1
    return {
        "total_cases": len(cases),
        "evaluated_cases": evaluated,
        "excluded_cases": dict(excluded),
        "by_kind": {kind: {o: counts[o] for o in OUTCOMES} for kind, counts in by_kind.items()},
    }
