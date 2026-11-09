import pytest
from eval_cases import SCORE_KEYS, Case
from report_check import check_form, grade_reports

KEYS = sorted(SCORE_KEYS)


def output(score=50, **by_key):
    scores = [{"key": key, "score": by_key.get(key, score)} for key in KEYS]
    total = round(sum(item["score"] or 0 for item in scores) / 6)
    return {"totalScore": total, "scores": scores}


def case(case_id, role=None, status="approved", kind="report", key="technical_reasoning", gap=10,
         version=1, pair_id="rp-1"):  # fmt: skip
    expectation = {
        "review": {"status": status, "author": "a", "reviewer": "b", "reviewed_at": "d",
                   "pending_notes": []},
        "allowed": [], "forbidden": [], "grader_controls": [],
    }  # fmt: skip
    if role:
        expectation["pair"] = {"pair_id": pair_id, "role": role, "key": key, "min_gap": gap}
    return Case(case_id, version, kind, "dev", "sg-1", {}, expectation)


def pair_cases(**options):
    return [case("r-1", "stronger", **options), case("r-2", "weaker", **options)]


def outputs(strong, weak):
    return {"r-1.v1": strong, "r-2.v1": weak}


def test_a_valid_output_has_no_form_problems():
    assert check_form(output()) == []
    assert check_form({**output(), "totalScore": 51}) == []  # within 1 of the mean 50


@pytest.mark.parametrize(
    "bad",
    [
        None,
        {},
        {"totalScore": 50, "scores": "x"},
        {"totalScore": 50, "scores": [{"key": "x", "score": 1}]},
        {**output(), "scores": output()["scores"][:5]},
        {**output(), "scores": output()["scores"] + output()["scores"][:1]},
        {**output(), "totalScore": 52},
        {**output(), "totalScore": 50.0},
        {**output(), "totalScore": True},
        {**output(), "totalScore": 101},
        output(technical_reasoning=45.5),
        output(communication=-1),
        output(problem_solving=None),
        {"scores": output()["scores"]},
    ],
    ids=["none", "empty", "scores not list", "unknown key", "five keys", "duplicate key",
         "total too far", "float total", "bool total", "total over 100", "float score",
         "negative score", "null score", "no total"],
)  # fmt: skip
def test_form_problems_are_reported(bad):
    assert check_form(bad)


def test_pair_passes_when_the_gap_reaches_min_gap():
    report = grade_reports(
        pair_cases(), outputs(output(technical_reasoning=80), output(technical_reasoning=70))
    )
    assert report["pairs"]["pass"] == 1
    assert report["details"][0]["gap"] == 10


@pytest.mark.parametrize("strong_score", [75, 70, 40])
def test_pair_fails_below_min_gap_or_reversed(strong_score):
    report = grade_reports(
        pair_cases(),
        outputs(output(technical_reasoning=strong_score + 0), output(technical_reasoning=70)),
    )
    assert report["pairs"]["fail"] == 1 and report["pairs"]["pass"] == 0


def test_only_the_pair_key_decides_the_order():
    strong = output(technical_reasoning=50, communication=100)
    weak = output(technical_reasoning=50, communication=0)
    assert grade_reports(pair_cases(), outputs(strong, weak))["pairs"]["fail"] == 1


def test_an_invalid_or_missing_output_is_never_a_pass():
    good = output(technical_reasoning=90)
    bad = {"totalScore": 50, "scores": []}
    assert grade_reports(pair_cases(), outputs(good, bad))["pairs"]["invalid_output"] == 1
    assert grade_reports(pair_cases(), {"r-1.v1": good})["pairs"]["missing_output"] == 1
    report = grade_reports(pair_cases(), outputs(good, bad))
    assert report["pairs"]["pass"] == 0 and "r-2.v1" in report["form_invalid"]


def test_unpaired_report_cases_are_counted_apart_and_never_pass():
    cases = [*pair_cases(), case("r-3")]
    report = grade_reports(
        cases, outputs(output(technical_reasoning=90), output(technical_reasoning=20))
    )
    assert report["unpaired_cases"] == ["r-3.v1"]
    assert report["evaluated_pairs"] == 1 and report["pairs"]["pass"] == 1


def test_form_check_covers_unpaired_outputs_too():
    cases = [*pair_cases(), case("r-3")]
    full = {**outputs(output(), output()), "r-3.v1": {"totalScore": 5, "scores": []}}
    assert "r-3.v1" in grade_reports(cases, full)["form_invalid"]


def test_unapproved_pairs_stay_out_of_the_quality_count_by_default():
    cases = pair_cases(status="unreviewed")
    given = outputs(output(technical_reasoning=90), output(technical_reasoning=20))
    report = grade_reports(cases, given)
    assert report["evaluated_pairs"] == 0 and report["excluded_pairs"] == {"unreviewed": 1}
    assert report["report_cases"] == 2
    assert grade_reports(cases, given, only_approved=False)["pairs"]["pass"] == 1


def test_other_case_kinds_are_ignored():
    report = grade_reports([case("q-1", kind="question")], {})
    assert report["report_cases"] == 0 and report["evaluated_pairs"] == 0


def test_versions_of_one_case_id_keep_their_own_outputs():
    # v1 pair fails, v2 pair passes; keyed by case_id alone both would read the v2 outputs
    cases = [
        case("r-1", "stronger", version=1), case("r-2", "weaker", version=1),
        case("r-1", "stronger", version=2, pair_id="rp-2"),
        case("r-2", "weaker", version=2, pair_id="rp-2"),
    ]  # fmt: skip
    given = {
        "r-1.v1": output(technical_reasoning=20), "r-2.v1": output(technical_reasoning=90),
        "r-1.v2": output(technical_reasoning=90), "r-2.v2": output(technical_reasoning=20),
        "r-2.v3": {"totalScore": 5, "scores": []},
    }  # fmt: skip
    report = grade_reports(cases, given)
    assert report["pairs"]["pass"] == 1 and report["pairs"]["fail"] == 1
    assert [d["outcome"] for d in report["details"]] == ["fail", "pass"]
    del given["r-1.v1"], given["r-2.v2"]  # a missing output stays with its own version
    assert [d["outcome"] for d in grade_reports(cases, given)["details"]] == [
        "missing_output",
        "missing_output",
    ]
    given["r-1.v1"], given["r-2.v1"] = output(), {"totalScore": 5, "scores": []}
    report = grade_reports(cases, given)
    assert report["details"][0]["outcome"] == "invalid_output"
    assert list(report["form_invalid"]) == ["r-2.v1"]
