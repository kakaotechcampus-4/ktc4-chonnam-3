import pytest
from eval_cases import Case
from grader_check import EXPECTED, check_grader

KINDS = sorted(EXPECTED)
ANSWERS = {f"out-{kind}": EXPECTED[kind] for kind in KINDS}  # kept outside the grader's view


def _case(case_id="q-1", status="approved"):
    review = {"status": status, "author": "a", "reviewer": "b", "reviewed_at": "2026-11-01"}
    expectation = {
        "allowed": [{"id": "a1"}],
        "forbidden": [{"id": "f1"}],
        "grader_controls": [{"kind": kind, "output": f"out-{kind}"} for kind in KINDS],
        "review": {**review, "pending_notes": []},
    }
    return Case(case_id, 1, "question", "dev", "sg-1", {}, expectation)


def _rate(report, outcome):
    return {kind: counts[outcome] for kind, counts in report["by_kind"].items()}


def test_perfect_grader_is_all_correct():
    report = check_grader([_case()], lambda rubric, output: ANSWERS[output])
    assert set(_rate(report, "correct").values()) == {1}
    for bad in ("false_accept", "false_reject", "abstained", "error"):
        assert set(_rate(report, bad).values()) == {0}


def test_always_accept_shows_false_accepts_per_kind():
    report = check_grader([_case()], lambda rubric, output: "accept")
    assert _rate(report, "false_accept") == {
        "allowed": 0,
        "forbidden": 1,
        "invalid_ref": 1,
        "tool_failure": 1,
        "ambiguous": 1,
    }
    assert _rate(report, "correct")["allowed"] == 1


def test_always_reject_shows_false_rejects_per_kind():
    report = check_grader([_case()], lambda rubric, output: "reject")
    assert _rate(report, "false_reject") == {
        "allowed": 1,
        "forbidden": 0,
        "invalid_ref": 0,
        "tool_failure": 0,
        "ambiguous": 1,
    }


def test_always_ambiguous_is_abstained_not_correct():
    report = check_grader([_case()], lambda rubric, output: "ambiguous")
    assert _rate(report, "abstained")["allowed"] == 1
    assert _rate(report, "correct")["ambiguous"] == 1
    assert _rate(report, "abstained")["ambiguous"] == 0


def test_grader_sees_only_rubric_and_output_not_the_kind():
    seen = []

    def spy(rubric, output):
        seen.append((rubric, output))
        return "accept"

    check_grader([_case()], spy)
    assert all(set(rubric) == {"allowed", "forbidden"} for rubric, _ in seen)
    assert {output for _, output in seen} == set(ANSWERS)


def test_grader_cannot_change_the_cases():
    case = _case()
    check_grader([case], lambda rubric, output: rubric["allowed"].clear() or "accept")
    assert case.expectation["allowed"] == [{"id": "a1"}]


def test_unreviewed_cases_count_in_total_but_not_in_quality():
    cases = [
        _case("q-1"),
        _case("q-2", "pending"),
        _case("q-3", "unreviewed"),
        _case("q-4", "invalid"),
    ]
    report = check_grader(cases, lambda rubric, output: ANSWERS[output])
    assert report["total_cases"] == 4
    assert report["evaluated_cases"] == 1
    assert report["excluded_cases"] == {"pending": 1, "unreviewed": 1, "invalid": 1}
    assert set(_rate(report, "correct").values()) == {1}


def test_crashing_grader_is_counted_not_hidden():
    def boom(rubric, output):
        raise RuntimeError("tool down")

    report = check_grader([_case()], boom)
    assert set(_rate(report, "error").values()) == {1}
    assert set(_rate(report, "correct").values()) == {0}


def test_unknown_verdict_is_rejected():
    with pytest.raises(ValueError, match="grader returned"):
        check_grader([_case()], lambda rubric, output: "maybe")


def test_approved_case_without_controls_is_not_counted_as_evaluated():
    empty = _case("q-2")
    empty.expectation["grader_controls"] = []
    calls = []

    def grader(rubric, output):
        calls.append(output)
        return ANSWERS[output]

    report = check_grader([_case("q-1"), empty], grader)
    assert len(calls) == len(KINDS)
    assert report["total_cases"] == 2
    assert report["evaluated_cases"] == 1
    assert report["excluded_cases"] == {"no_controls": 1}


def test_async_controls_keep_the_same_review_exclusion_and_error_policy():
    import asyncio

    import grader_check

    assert hasattr(grader_check, "check_grader_async"), "비동기 Judge 교정 경계가 필요하다"
    seen = []

    async def judge(rubric, output):
        seen.append((rubric, output))
        return ANSWERS[output]

    report = asyncio.run(grader_check.check_grader_async([_case(), _case("q-2", "pending")], judge))
    assert len(seen) == len(KINDS)
    assert report["excluded_cases"] == {"pending": 1}
    assert set(_rate(report, "correct").values()) == {1}
    assert all(set(rubric) == {"allowed", "forbidden"} for rubric, _ in seen)
    assert all("kind" not in record["judge"] for record in report["controls"])


def test_async_judge_failure_keeps_input_hashes_without_exception_body():
    import asyncio

    import grader_check

    async def broken(rubric, output):
        raise RuntimeError("private exception body")

    report = asyncio.run(grader_check.check_grader_async([_case()], broken))
    first = report["controls"][0]["judge"]
    assert len(first["metadata"]["rubric_sha256"]) == 64
    assert len(first["metadata"]["candidate_sha256"]) == 64
    assert "private exception body" not in str(report)
