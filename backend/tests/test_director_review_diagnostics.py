async def test_model_alias_and_actual_snapshot_are_separately_bound_without_changing_outcome():
    class SnapshotProvider(Provider):
        async def __call__(self, request, validator):
            result = await super().__call__(request, validator)
            return replace(
                result,
                attempts=tuple(
                    replace(attempt, model="actual-model-snapshot") for attempt in result.attempts
                ),
            )

    provider = SnapshotProvider()
    provider.review["wording_valid"] = True
    saved = await run_cases([case()], executor(provider), metadata={})
    row = saved["cases"][0]
    assert row["status"] == "succeeded"
    assert row.get("diagnostics") is not None
    review = row["diagnostics"]["reviews"][0]
    assert review["response_model"] == "actual-model-snapshot"
    assert row["source_snapshot"]["requests"][1]["model"] == "fixture-model"
    assert len(review_packets([case()], saved)) == 1
    review["response_model"] = "changed-model"
    row["diagnostics_hash"] = content_hash(row["diagnostics"])
    with pytest.raises(ValueError, match="diagnostic"):
        review_packets([case()], saved)
