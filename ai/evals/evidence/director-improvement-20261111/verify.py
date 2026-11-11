"""공개 발췌의 합계와 연결을 검사한다. 네트워크·모델·DB를 호출하지 않는다."""

from __future__ import annotations

import hashlib
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, cast

HERE = Path(__file__).resolve().parent
FLAGS = ("plan_valid", "context_valid", "wording_valid", "contract_matches")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def load(name: str) -> dict[str, Any]:
    value = json.loads((HERE / name).read_text(encoding="utf-8"))
    require(isinstance(value, dict), name + ": expected object")
    return cast(dict[str, Any], value)


def review_outcome(raw: dict[str, Any]) -> tuple[str, str | None]:
    require(all(type(raw[key]) is bool for key in (*FLAGS, "safe_alternative")), "flag type")
    unasked = any(point["status"] != "asked" for point in raw["point_coverage"])
    if all(raw[key] for key in FLAGS) and not unasked:
        return "accept", None
    if not raw["safe_alternative"]:
        return "reject", "no_valid_candidate"
    if not raw["plan_valid"] or not raw["context_valid"]:
        return "reject", "replan"
    return "reject", "rewrite"


def check_quotes(question: dict[str, Any], raw: dict[str, Any]) -> None:
    points = question["question_contract"]["required_points"]
    keys = [point["key"] for point in points]
    actual = [point["key"] for point in raw["point_coverage"]]
    require(len(keys) == len(set(keys)) and set(keys) == set(actual), "point keys")
    require(len(actual) == len(set(actual)), "duplicate point coverage")
    for point in raw["point_coverage"]:
        excerpt = point["question_excerpt"]
        require(isinstance(excerpt, str), "excerpt must be string")
        if point["status"] == "asked":
            require(bool(excerpt), "asked needs nonempty quote")
        if excerpt:
            require(excerpt in question["text"], "noncontiguous question quote")


def check_files() -> None:
    provenance = load("provenance.json")
    hashes = provenance["public_file_hashes"]
    require(len(hashes) == 9, "nine files plus provenance expected")
    require(
        set(hashes) | {"provenance.json"}
        == {path.name for path in HERE.iterdir() if path.is_file()},
        "file set",
    )
    for name, expected in hashes.items():
        require(Path(name).name == name, "manifest path must be filename")
        actual = hashlib.sha256((HERE / name).read_bytes()).hexdigest()
        require(actual == expected, name + ": SHA256 mismatch")
    for path in HERE.glob("*.json"):
        text = path.read_text(encoding="utf-8")
        require("\ufffd" not in text, "invalid Unicode replacement")
        require(
            not re.search(r"(?:^|[\s\"])[A-Za-z]:[\\/]|/Users/|/home/", text),
            "private absolute path",
        )
        require(
            not re.search(r"\b[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\b", text, re.I),
            "unmapped UUID",
        )


def check_summary() -> None:
    summary = load("summary.json")
    total, cohorts = summary["total"], summary["cohorts"]
    require(len(cohorts) == 13 and len({row["cohort"] for row in cohorts}) == 13, "cohort IDs")
    for field, expected in [
        ("physical_calls", 1254),
        ("input_tokens", 11227216),
        ("output_tokens", 2062870),
        ("unknown_usage_calls", 0),
    ]:
        require(sum(row[field] for row in cohorts) == total[field] == expected, field)
    require(
        total["unique_call_ids"] == 1254 and total["duplicates"] == [],
        "private uniqueness assertion",
    )
    require(total["actual_billed_cost"] is None, "billing remains unverified")
    for cohort in cohorts:
        require(cohort["models"] == {"gpt-6-luna": cohort["physical_calls"]}, "Luna-only cohort")
        require(sum(cohort["operations"].values()) == cohort["physical_calls"], "operation count")
    partition = summary["l_call_partition"]
    require(
        partition["actual_review"]
        + partition["actual_generation_plan_review"]
        + partition["actual_scope_review"]
        == partition["actual_total"]
        == 32,
        "L physical partition",
    )
    api0 = summary["api0"]
    require(api0["counted_in_actual_total"] is False, "Mock separated")
    for name, count in [("l_final_primary", 24), ("l_final_additional", 8)]:
        require(
            api0[name]["physical_model_calls"] == 0 and api0[name]["mock_responses"] == count,
            "API0 counts",
        )
        require(api0[name]["proof_passed"] is True, "API0 final proof")
    failure = api0["l_first_additional_failure"]
    require(
        failure["mock_responses"] == 1
        and failure["physical_model_calls"] == 0
        and failure["not_final_proof"] is True,
        "first Mock failure retained",
    )
    require(
        summary["development_and_final"]["latest_policy_final_groups_actually_run"] == 0,
        "holdout not run",
    )


def check_semantic_fit() -> None:
    evidence = load("semantic-fit-cases.json")
    cases = evidence["cases"]
    require(len(cases) == 12 and evidence["physical_model_calls"] == 24, "12 pairs/24 calls")
    require(
        Counter(row["oracle"]["expected_source_verdict"] for row in cases)
        == {"accept": 6, "reject": 6},
        "6 positive/6 negative",
    )
    counts: dict[str, Counter[str]] = {"A": Counter(), "B": Counter()}
    for case in cases:
        require({row["arm"] for row in case["actual_observations"]} == {"A", "B"}, "A/B pair")
        for row in case["actual_observations"]:
            arm, oracle = row["arm"], case["oracle"]
            check_quotes(case["question"], row["raw_review"])
            verdict, recovery = review_outcome(row["raw_review"])
            match = verdict == oracle["expected_source_verdict"]
            strict = match and recovery == (
                None if oracle["expected_recovery"] == "none" else oracle["expected_recovery"]
            )
            require(
                verdict == row["model_verdict"] and recovery == row["model_recovery"],
                "actual verdict mapping",
            )
            require(
                match == row["oracle_verdict_match"] and strict == row["oracle_recovery_match"],
                "stored match",
            )
            counts[arm]["match"] += int(match)
            counts[arm]["strict"] += int(strict)
            counts[arm]["false_accept"] += int(
                oracle["expected_source_verdict"] == "reject" and verdict == "accept"
            )
            counts[arm]["positive_preserved"] += int(
                oracle["expected_source_verdict"] == "accept" and verdict == "accept"
            )
    require([counts[arm]["match"] for arm in ["A", "B"]] == [6, 12], "6/12 to 12/12")
    require([counts[arm]["strict"] for arm in ["A", "B"]] == [6, 12], "strict recovery")
    require([counts[arm]["false_accept"] for arm in ["A", "B"]] == [6, 0], "false accept 6 to 0")
    require(
        [counts[arm]["positive_preserved"] for arm in ["A", "B"]] == [6, 6], "positive preservation"
    )


def check_generation_and_scope() -> None:
    evidence = load("semantic-fit-generation.json")
    rows = evidence["observations"]
    generation = [row for row in rows if row["kind"] == "generation"]
    scope = [row for row in rows if row["kind"] == "scope"]
    require(len(generation) == 2 and len(scope) == 4, "generation2 and scope2 pairs")
    require(
        evidence["physical_model_calls"] == 2 * len(generation) + len(scope) == 8,
        "Plan/Review physical denominator",
    )
    require(evidence["actual_t3_calls"] == 0, "synthetic analysis not actual T3")
    require(
        {row["question_length_codepoints"] for row in generation} == {87, 196},
        "actual question lengths",
    )
    for row in rows:
        check_quotes(row["question"], row["raw_review"])
        require(
            len(row["question"]["text"]) == row["question_length_codepoints"], "codepoint length"
        )
        verdict, _ = review_outcome(row["raw_review"])
        require(verdict == row["actual_review_verdict"], "probe Review mapping")
        require(
            (verdict == row["source_verdict"]) == row["source_and_review_agree"],
            "probe disagreement retained",
        )
    require(all(row["source_verdict"] == "accept" for row in scope), "scope acceptance")
    require(
        sum(row["source_and_review_agree"] for row in generation) == 1,
        "one generated disagreement retained",
    )


def check_review_calibration() -> None:
    evidence = load("review-calibration-cases.json")
    cases = evidence["cases"]
    require(len(cases) == 8 and evidence["physical_model_calls"] == 16, "J8 pairs/16 calls")
    counts: Counter[str] = Counter()
    for case in cases:
        for row in case["actual_observations"]:
            check_quotes(case["question"], row["raw_review"])
            verdict, recovery = review_outcome(row["raw_review"])
            require(
                (verdict, recovery) == (row["actual_verdict"], row["actual_recovery"]),
                "J outcome mapping",
            )
            match = verdict == case["oracle"]["expected_source_verdict"]
            require(match == row["decision_match"], "J stored decision match")
            counts[row["arm"]] += int(match)
    require([counts[arm] for arm in ["A", "B"]] == [4, 8], "J4/8 to 8/8")


def check_answer_scope() -> None:
    evidence = load("answer-scope-cases.json")
    require(
        len(evidence["cases"]) == 2 and evidence["physical_calls"] == 5, "claim4 plus refinement1"
    )
    count: Counter[str] = Counter()
    for case in evidence["cases"]:
        require(case["synthetic_answer"] is True, "synthetic answer marker")
        for row in case["actual_observations"]:
            count[row["arm"]] += int(
                row["codex_source_grade"]["focused_claim_scope_verdict"] == "accept"
            )
            for claim in row["codex_source_grade"]["claims"]:
                require(
                    claim["claim_text"] in case["answer_text"], "claim literal answer substring"
                )
            for claim in row["raw"]["claim_checks"]:
                if "claim_excerpt" in claim:
                    require(
                        bool(claim["claim_excerpt"])
                        and claim["claim_excerpt"] in case["answer_text"],
                        "v7 excerpt",
                    )
    require([count[arm] for arm in ["A", "B"]] == [0, 2], "claim scope comparison")
    require(
        evidence["targeted_refinement"]["current_contribution_scope"]["raw"]["scope"] == "unknown",
        "future proposal contribution unknown",
    )


def check_service_flow() -> None:
    evidence = load("service-flow-summary.json")
    turns, generations = evidence["turns"], evidence["generations"]
    require([row["turn_no"] for row in turns] == list(range(1, 10)), "nine turns")
    require(
        Counter(row["question"]["persona"] for row in turns)
        == {"hr_manager": 1, "tech_lead": 6, "domain_lead": 2},
        "persona quota",
    )
    require(len(generations) == evidence["actual_call_count"] == 27, "K27 physical requests")
    require(
        Counter(row["operation"] for row in generations)
        == evidence["operation_counts"]
        == {"plan": 9, "review": 9, "answer_analysis.initial": 9},
        "operation counts",
    )
    require(
        evidence["actual_retries_rejections_tools"] == 0
        and evidence["latest_semantic_fit_nine_turn_run"] is False,
        "K scope",
    )
    db = evidence["database_audit"]
    require(
        db["passed"] is True and db["replays"] == 10 and db["retry_entries"] == 0,
        "DB snapshot audit assertion",
    )
    for row in turns:
        require(row["synthetic_answer"] is True, "synthetic K answer")
        for claim in row["raw_answer_assessment"]["claim_checks"]:
            require(claim["claim_excerpt"] in row["answer_text"], "K claim answer substring")
    observed = sum(row["observed_generation_seconds"] for row in generations)
    require(
        math.isclose(
            observed,
            evidence["timing"]["generation_observed_seconds_sum"]["complete_total"],
            abs_tol=1e-8,
        ),
        "observed seconds sum",
    )


def _check_publication_test_reports(value: dict[str, Any]) -> None:
    for group in (
        "latest_ai",
        "prior_actual_rollout_timer_catalog12",
        "latest_561_catalog11_smoke",
        "latest_registration_compatibility",
        "published_core_smoke",
        "final_backend_full",
        "ledger_gateway_timing_related",
    ):
        report = next(row for row in value["tests"] if row["group"] == group)
        require(
            report["status"] == "passed" and report["tests"] > 0, "test report " + group
        )
        require(
            report["passed"] + report["failures"] + report["errors"] + report["skipped"]
            == report["tests"],
            "test denominator",
        )
    require(
        value["quality_limits"]["new_holdout_groups_run"] == 0, "holdout still separate"
    )
    require(
        value["quality_limits"]["whole_user_browser_voice_report_e2e"] is False,
        "partial service scope",
    )
    require(
        all(number == 0 for number in value["export_side_effects"].values()),
        "export adds no calls",
    )


def _check_publication_backend_execution(value: dict[str, Any]) -> None:
    binding = value["backend_execution_binding"]
    require(
        binding["status"] == "verified_completed",
        "completed backend execution and source binding",
    )
    source = binding["source_copy_verification"]
    require(
        source["file_count"]
        == source["raw_sha256_matches"]
        == source["git_blobs_verified_exact"]
        == 1417,
        "all frozen source copy files checked",
    )
    require(
        source["recorded_git_tree_matches"] is True,
        "source Git tree locally reconstructed",
    )
    require(
        source["reconstructed_git_tree"] == binding["source_normalized_git_tree"],
        "source tree equality",
    )
    require(
        source["source_files_modified"] == source["refs_or_commits_created"] == 0,
        "snapshot leaves original source and refs untouched",
    )
    require(
        source["actual_source_index_modified"] is False,
        "original source index preserved",
    )
    require(
        source["whole_manifest_publicly_included"] is False,
        "private full-manifest limit retained",
    )
    execution = binding["execution"]
    require(
        execution["phase"] == "full" and execution["exit_code"] == 0,
        "full backend process success",
    )
    require(
        execution["finished_at"] is not None and execution["started_at"] is not None,
        "full run completed timestamps",
    )
    require(
        execution["source_snapshot_mount_read_only"] is True
        and execution["executed_source_copy_git_exact"] is True,
        "read-only exact source copy",
    )
    require(
        execution["postgres_data_tmpfs"] is True
        and execution["disk_durability_or_crash_test"] is False,
        "logical tmpfs validation scope",
    )
    require(
        execution["provider_api_calls"] == execution["package_installs"] == 0,
        "backend validation adds no provider calls or installs",
    )
    workspace = binding["workspace_postcheck"]
    require(
        workspace["git_exact_files_before_run"] == 1417
        and workspace["changed_source_files_after_run"] == [],
        "executed source unchanged after full run",
    )
    report = next(row for row in value["tests"] if row["group"] == "final_backend_full")
    require(
        binding["xml_sha256"] == report["sha256"]
        and binding["xml_count_binding_verified"] is True,
        "execution metadata bound to final XML",
    )
    require(
        report["passed"] == 3302
        and report["failures"] == report["errors"] == report["skipped"] == 0,
        "final 3302 full backend tests",
    )
    versions = binding["versions"]["runtime_query_receipt"]
    require(
        versions["image_id"] == execution["image"]
        and versions["package_installs"] == versions["provider_model_calls"] == 0,
        "read-only same-image version receipt",
    )
    require(
        versions["versions"]["python"] == "3.12.15"
        and versions["versions"]["pytest"] == "9.1.1",
        "observed Python and pytest versions",
    )
    for selected in binding["selected_executed_source_files"]:
        require(
            selected["line_ending_relationship_verified"] is True,
            "selected raw and Git source relationship checked",
        )
        require(
            selected["raw_bytes_equal"] is not selected["only_crlf_to_lf_difference"],
            "explicit measured byte equality or CRLF-only distinction",
        )
        require(
            (selected["sha256"] == selected["current_working_tree_raw_sha256"])
            == selected["raw_bytes_equal"],
            "separate exact source byte hashes",
        )
    repo = HERE.parents[3]
    if (repo / "ai/src/devon_ai").is_dir():
        for selected in binding["selected_executed_source_files"]:
            product = repo / selected["path"]
            allowed_raw_sha = {
                selected["sha256"],
                selected["current_working_tree_raw_sha256"],
            }
            require(
                product.is_file()
                and hashlib.sha256(product.read_bytes()).hexdigest() in allowed_raw_sha,
                "executed selected source including registration fix",
            )
    line_endings = binding["selected_source_line_endings"]
    require(
        line_endings["direct_byte_equal_count"]
        + line_endings["crlf_working_tree_vs_lf_git_count"]
        == len(binding["selected_executed_source_files"]),
        "source line-ending denominator",
    )
    require(
        binding["additional_model_or_http_or_business_db_calls"] == 0,
        "source binding adds no API calls",
    )


def check_publication_validation() -> None:
    path = HERE / "publication-validation.json"
    if not path.exists():
        return
    value = load("publication-validation.json")
    _check_publication_runtime(value)
    _check_publication_calls(value)
    _check_publication_turns(value)
    _check_publication_reviews(value)
    _check_publication_session(value)
    _check_publication_compatibility(value)
    _check_publication_test_reports(value)
    _check_publication_backend_execution(value)


def main() -> None:
    check_files()
    check_summary()
    check_semantic_fit()
    check_generation_and_scope()
    check_review_calibration()
    check_answer_scope()
    check_service_flow()
    check_publication_validation()
    sys.stdout.write(
        json.dumps(
            {
                "status": "passed",
                "actual_model_or_api_or_db_calls_added": 0,
                "scope": "published excerpt arithmetic, classifications and literal bindings only",
            }
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
