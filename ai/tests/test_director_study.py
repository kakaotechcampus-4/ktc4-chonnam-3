"""합성 코호트의 누수·정답 유출과 비교 분모 오류를 방지한다."""

import copy

import pytest
from director_cases import build_cohort, control_packets, export_cohort, validate_cohort
from director_rubrics import compile_criteria, derive_verdict
from director_study import compare_runs
from eval_cases import load_cases


def test_pilot_is_a_subset_and_holdout_has_different_sources():
    cohort = build_cohort()
    assert len(cohort.cases) == 120
    dev = {case.case_id for case in cohort.select("dev")}
    pilot = {case.case_id for case in cohort.select("pilot")}
    holdout = cohort.select("holdout")
    assert len(dev) == 60 and len(pilot) == 12 and pilot <= dev
    assert len(holdout) == 60
    assert {case.source_group_id for case in cohort.select("dev")}.isdisjoint(
        case.source_group_id for case in holdout
    )
    validate_cohort(cohort)


def test_typed_cases_keep_actual_answers_locations_and_no_expected_labels(tmp_path):
    from devon_ai import contracts as c

    cohort = build_cohort()
    export_cohort(cohort, tmp_path)
    loaded = load_cases(tmp_path)
    assert len(loaded) == 120
    for case in loaded:
        data = case.model_input()["service_input"]
        context = c.decode_strict(c.Context, data["context"])
        assert context.history[-1].answer == data["answer_text"]
        assert context.evidence[0].git_ref == context.repositories[0].git_ref
        assert context.evidence[0].start_line == 1
        assert set(case.model_input()) == {"service_task", "service_input"}
        assert "expected_verdict" not in data and "source_group_id" not in data


def test_same_source_in_both_splits_is_rejected():
    cohort = build_cohort()
    first = cohort.cases[0]
    other = cohort.select("holdout")[0]
    from dataclasses import replace

    wrong = replace(other, source_group_id=first.source_group_id)
    with pytest.raises(ValueError, match="source group"):
        validate_cohort(replace(cohort, cases=(first, wrong)))


def test_renaming_a_source_cannot_move_identical_original_text_into_holdout():
    from dataclasses import replace

    cohort = build_cohort()
    first = cohort.select("dev")[0]
    other = cohort.select("holdout")[0]
    payload = other.model_input()
    payload["service_input"]["context"]["evidence"][0]["content"] = first.payload["service_input"][
        "context"
    ]["evidence"][0]["content"]
    changed = tuple(
        replace(case, payload=payload) if case.case_id == other.case_id else case
        for case in cohort.cases
    )
    with pytest.raises(ValueError, match="source text"):
        validate_cohort(replace(cohort, cases=changed))


def test_manifest_does_not_accept_silently_changed_answers():
    from dataclasses import replace

    cohort = build_cohort()
    first = cohort.cases[0]
    payload = first.model_input()
    payload["service_input"]["answer_text"] = "변경된 답변"
    with pytest.raises(ValueError, match="manifest"):
        validate_cohort(replace(cohort, cases=(replace(first, payload=payload), *cohort.cases[1:])))


def test_controls_hide_expected_kind_but_keep_incomplete_observation():
    cohort = build_cohort()
    packets, labels = control_packets(cohort)
    assert len(packets) == 24
    assert list(labels.values()).count("accept") == 8
    assert list(labels.values()).count("reject") == 8
    assert list(labels.values()).count("ambiguous") == 8
    for packet in packets:
        assert "expected_verdict" not in packet and "kind" not in packet
        assert set(packet["binding"]) == {
            "rubric_sha256",
            "candidate_sha256",
            "source_context_sha256",
        }


def test_alternatives_are_one_criterion_and_not_multiple_obligations():
    rubric = compile_criteria("tool_unavailable")
    alternatives = [item for item in rubric["allowed"] if item["id"] == "next_action"]
    assert len(alternatives) == 1
    assert "하나" in alternatives[0]["purpose"]
    ids = [f"{group}:{item['id']}" for group in ("allowed", "forbidden") for item in rubric[group]]
    statuses = {identifier: "satisfied" for identifier in ids}
    assert derive_verdict(rubric, statuses) == "accept"
    statuses[ids[0]] = "unclear"
    assert derive_verdict(rubric, statuses) == "ambiguous"
    statuses[ids[-1]] = "violated"
    assert derive_verdict(rubric, statuses) == "reject"
    with pytest.raises(ValueError, match="criterion"):
        derive_verdict(rubric, {ids[0]: "satisfied"})


def result(case_id="case-1", **row):
    return {
        "metadata": {"study": {"settings_sha256": "settings", "cohort_sha256": "cohort"}},
        "cases": [
            {
                "case": case_id,
                "source_group_id": "group-1",
                "input_hash": "input",
                "expectation_hash": "criteria",
                "status": "succeeded",
                "service_latency_ms": 100,
                "latency_ms": 999,
                "attempts": [{"input_tokens": 10, "output_tokens": 5}],
                "cost_usd": None,
                "diagnostic_judge": {"verdict": "accept"},
                **row,
            }
        ],
    }


def test_pair_comparison_uses_service_time_and_preserves_unknown_cost():
    compared = compare_runs(result(), result(service_latency_ms=70, latency_ms=2000))
    assert compared["pairs"][0]["service_latency_delta_ms"] == -30
    assert compared["summary"]["paired_cases"] == 1
    assert compared["summary"]["quality_regressions"] == 0
    assert compared["summary"]["cost_delta_usd"] is None
    assert compared["summary"]["source_groups"] == 1


@pytest.mark.parametrize("change", ["input", "criteria", "settings", "missing", "duplicate"])
def test_comparison_refuses_unmatched_or_changed_experiment(change):
    before, after = result(), copy.deepcopy(result())
    if change == "input":
        after["cases"][0]["input_hash"] = "different"
    elif change == "criteria":
        after["cases"][0]["expectation_hash"] = "different"
    elif change == "settings":
        after["metadata"]["study"]["settings_sha256"] = "different"
    elif change == "missing":
        after["cases"] = []
    else:
        after["cases"].append(copy.deepcopy(after["cases"][0]))
    with pytest.raises(ValueError):
        compare_runs(before, after)


def test_execution_failure_and_unjudged_output_cannot_be_quality_passes():
    compared = compare_runs(result(), result(status="failed", diagnostic_judge=None))
    assert compared["summary"]["candidate_execution_failures"] == 1
    assert compared["summary"]["candidate_quality_unknown"] == 1
    assert compared["summary"]["candidate_quality_passes"] == 0


def test_failed_service_wait_and_usage_are_reported_outside_success_latency():
    compared = compare_runs(
        result(status="failed", service_latency_ms=700, diagnostic_judge=None),
        result(service_latency_ms=80),
    )
    assert compared["summary"]["timed_success_pairs"] == 0
    assert compared["summary"]["median_service_latency_delta_ms"] is None
    assert compared["summary"]["baseline_failures"]["service_latency_ms"] == 700
    assert compared["summary"]["baseline_failures"]["input_tokens"] == 10
    assert compared["summary"]["baseline_failures"]["attempt_records"] == 1
