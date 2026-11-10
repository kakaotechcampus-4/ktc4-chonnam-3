"""Checks a grader against reviewed control outputs. Not part of the runtime package.

ADR 0009: a grader is tried on allowed, forbidden, ambiguous, invalid-reference and
tool-failure controls, and false accepts and false rejects are counted per control kind.
Cases that are not approved stay in the totals but out of the quality denominator.
"""

from __future__ import annotations

import copy
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import asdict
from typing import Any

from async_grader import VERDICTS
from eval_cases import CONTROL_KINDS, Case
from judge_context import build_judge_context

# Candidate expectation for each control kind (author assumption, pending team review).
EXPECTED = {
    "allowed": "accept",
    "forbidden": "reject",
    "invalid_ref": "reject",
    "tool_failure": "reject",
    "ambiguous": "ambiguous",
}
_WRONG = {"accept": "false_accept", "reject": "false_reject", "ambiguous": "abstained"}
OUTCOMES = ("correct", "false_accept", "false_reject", "abstained", "error")

# The grader sees the rubric (allowed, forbidden) and one output, never the control kind.
Grader = Callable[[dict[str, Any], str], str]


def _outcome(kind: str, verdict: object) -> str:
    if type(verdict) is not str or verdict not in VERDICTS:
        raise ValueError("grader returned an unknown verdict")
    return "correct" if verdict == EXPECTED[kind] else _WRONG[verdict]


def _reviewed(cases: Sequence[Case]) -> tuple[list[Case], Counter[str]]:
    reviewed, excluded = [], Counter[str]()
    for case in cases:
        status = case.expectation["review"]["status"]
        if status != "approved":
            excluded[status] += 1
        elif not case.expectation["grader_controls"]:
            excluded["no_controls"] += 1
        else:
            reviewed.append(case)
    return reviewed, excluded


def _report(
    cases: Sequence[Case],
    reviewed: Sequence[Case],
    excluded: Counter[str],
    by_kind: dict[str, Counter[str]],
) -> dict[str, Any]:
    return {
        "total_cases": len(cases),
        "evaluated_cases": len(reviewed),
        "excluded_cases": dict(excluded),
        "by_kind": {
            kind: {outcome: counts[outcome] for outcome in OUTCOMES}
            for kind, counts in by_kind.items()
        },
    }


def check_grader(cases: Sequence[Case], grader: Grader) -> dict[str, Any]:
    by_kind = {kind: Counter[str]() for kind in sorted(CONTROL_KINDS)}
    reviewed, excluded = _reviewed(cases)
    for case in reviewed:
        rubric = {k: case.expectation[k] for k in ("allowed", "forbidden")}
        for control in case.expectation["grader_controls"]:
            try:
                got = grader(copy.deepcopy(rubric), control["output"])
            except Exception:  # a crashing grader is a result, not a skipped case
                by_kind[control["kind"]]["error"] += 1
                continue
            outcome = _outcome(control["kind"], got)
            by_kind[control["kind"]][outcome] += 1
    return _report(cases, reviewed, excluded, by_kind)


async def check_grader_async(cases: Sequence[Case], grader: Any) -> dict[str, Any]:
    from async_grader import Judgment, call_grader

    reviewed, excluded = _reviewed(cases)
    by_kind = {kind: Counter[str]() for kind in sorted(CONTROL_KINDS)}
    controls = []
    for case in reviewed:
        rubric = {key: case.expectation[key] for key in ("allowed", "forbidden")}
        for index, control in enumerate(case.expectation["grader_controls"]):
            try:
                result = await call_grader(
                    grader,
                    rubric,
                    control["output"],
                    source_context=build_judge_context(case.model_input()),
                )
            except Exception as error:
                result = Judgment(
                    None, failure={"stage": "judge", "error_code": type(error).__name__}
                )
            if result.failure is not None:
                by_kind[control["kind"]]["error"] += 1
            else:
                by_kind[control["kind"]][_outcome(control["kind"], result.verdict)] += 1
            # 정답 종류는 채점기 호출이 끝난 뒤 로컬 감사 기록에만 연결한다.
            controls.append(
                {
                    "case": f"{case.case_id}.v{case.version}",
                    "control_index": index,
                    "control_kind": control["kind"],
                    "expected_verdict": EXPECTED[control["kind"]],
                    "judge": asdict(result),
                }
            )
    return {**_report(cases, reviewed, excluded, by_kind), "controls": controls}
