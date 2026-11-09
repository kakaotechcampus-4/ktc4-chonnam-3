"""Grades report outputs: score form checks and score-order pairs. Not part of the runtime package.

Rules: ai/evals/README.md (report cases) and ADR 0009. An output is the public report shape
`{"totalScore": int, "scores": [{"key": ..., "score": int}, ...]}`; narrative is not graded here.
Cases that are not approved stay in the totals but out of the quality denominator.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from eval_cases import SCORE_KEYS, Case

OUTCOMES = ("pass", "fail", "invalid_output", "missing_output")


def _score(value: Any) -> bool:
    return type(value) is int and 0 <= value <= 100  # bool is an int subclass


def check_form(output: Any) -> list[str]:
    """Problems with one report output's score form; an empty list means the form is valid."""
    scores = output.get("scores") if isinstance(output, dict) else None
    if not isinstance(scores, list) or not all(isinstance(item, dict) for item in scores):
        return ["scores must be a list of objects"]
    keys = [item.get("key") for item in scores]
    if not all(isinstance(key, str) for key in keys) or sorted(keys) != sorted(SCORE_KEYS):
        return ["scores must hold each of the six keys exactly once"]
    problems = [f"score for {item['key']} must be an integer from 0 to 100"
                for item in scores if not _score(item.get("score"))]  # fmt: skip
    total = output.get("totalScore")
    if not _score(total):
        problems.append("totalScore must be an integer from 0 to 100")
    if not problems and abs(total - sum(item["score"] for item in scores) / len(scores)) > 1:
        problems.append("totalScore must be within 1 of the mean of the six scores")
    return problems


def _stem(case: Case) -> str:
    return f"{case.case_id}.v{case.version}"  # case_id alone would merge v1 and v2


def _key_score(output: Mapping[str, Any], key: str) -> int:
    return int(next(item["score"] for item in output["scores"] if item["key"] == key))


def grade_reports(
    cases: Sequence[Case], outputs: Mapping[str, Any], *, only_approved: bool = True
) -> dict[str, Any]:
    """Form-check every report output and judge each pair; keys of outputs are `r-0001.v1` stems.

    A pair passes when the stronger case's key score beats the weaker one's by at least min_gap.
    A pair with an invalid or missing output is never a pass. Report cases without a pair are
    counted apart and are not passes. With only_approved, a pair needs both cases approved to count.
    """
    reports = [case for case in cases if case.kind == "report"]
    form = {
        _stem(case): problems
        for case in reports
        if _stem(case) in outputs and (problems := check_form(outputs[_stem(case)]))
    }
    pairs: dict[str, list[Case]] = {}
    for case in reports:
        if "pair" in case.expectation:
            pairs.setdefault(case.expectation["pair"]["pair_id"], []).append(case)
    counts: Counter[str] = Counter()
    excluded: Counter[str] = Counter()
    details = []
    for pair_id, members in sorted(pairs.items()):
        statuses = {case.expectation["review"]["status"] for case in members}
        if only_approved and statuses != {"approved"}:
            excluded[sorted(statuses - {"approved"})[0]] += 1
            continue
        pair = members[0].expectation["pair"]
        by_role = {case.expectation["pair"]["role"]: _stem(case) for case in members}
        strong, weak = (outputs.get(by_role[role]) for role in ("stronger", "weaker"))
        gap = None
        if strong is None or weak is None:
            outcome = "missing_output"
        elif check_form(strong) or check_form(weak):
            outcome = "invalid_output"
        else:
            gap = _key_score(strong, pair["key"]) - _key_score(weak, pair["key"])
            outcome = "pass" if gap >= pair["min_gap"] else "fail"
        counts[outcome] += 1
        details.append(
            {
                "pair_id": pair_id,
                "key": pair["key"],
                "min_gap": pair["min_gap"],
                "gap": gap,
                "outcome": outcome,
            }  # fmt: skip
        )
    return {
        "report_cases": len(reports),
        "pairs": {o: counts[o] for o in OUTCOMES},
        "evaluated_pairs": sum(counts.values()),
        "excluded_pairs": dict(excluded),
        "unpaired_cases": sorted(_stem(c) for c in reports if "pair" not in c.expectation),
        "form_invalid": form,
        "details": details,
    }
