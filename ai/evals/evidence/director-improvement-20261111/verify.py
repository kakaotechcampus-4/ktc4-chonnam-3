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


def main() -> None:
    check_files()
    check_summary()
    check_semantic_fit()
    check_generation_and_scope()
    check_review_calibration()
    check_answer_scope()
    check_service_flow()
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
