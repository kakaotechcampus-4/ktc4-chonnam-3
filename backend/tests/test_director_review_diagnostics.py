def test_private_attempt_json_hash_binds_json_types_and_ignores_serialization_spacing():
    attempt = c.AttemptMetadata(
        1, "fixture", "fixture-model", "director_v2", "director-review.v1", 1, 2, 3
    )
    variants = (
        '{"flag": true, "reason": "x"}',
        '{ "reason": "x", "flag": true }',
        '{"flag": 1, "reason": "x"}',
    )
    records = [_attempts([replace(attempt, raw_output=raw)])[0] for raw in variants]
    boolean_hash = hashlib.sha256(b'{"flag":true,"reason":"x"}').hexdigest()
    number_hash = hashlib.sha256(b'{"flag":1,"reason":"x"}').hexdigest()
    assert [row["raw_output_json_sha256"] for row in records] == [
        boolean_hash,
        boolean_hash,
        number_hash,
    ]
    assert records[0]["raw_output_sha256"] != records[1]["raw_output_sha256"]
    assert boolean_hash != number_hash
    assert all("raw_output" not in row for row in records)


@pytest.mark.parametrize("raw", [None, "", "not-json", "{", "NaN", '{"flag":true,"flag":false}'])
def test_unparseable_private_attempt_has_no_json_content_hash(raw):
    attempt = c.AttemptMetadata(
        1, "fixture", "fixture-model", "director_v2", "director-review.v1", 1, 2, 3, raw_output=raw
    )
    record = _attempts([attempt])[0]
    assert record["raw_output_json_sha256"] is None
    assert record["raw_output_sha256"] == (
        hashlib.sha256(raw.encode()).hexdigest() if raw is not None else None
    )


async def test_v2_rejudge_rejects_missing_canonical_response_hash():
    provider = Provider()
    provider.review["wording_valid"] = True
    saved = await run_cases([case()], executor(provider), metadata={})
    row = saved["cases"][0]
    assert row["diagnostics"]["schema_version"] == "director-diagnostics.v2"
    del row["attempts"][1]["raw_output_json_sha256"]
    with pytest.raises(ValueError, match="diagnostic"):
        review_packets([case()], saved)


async def test_legacy_v1_rejudge_preserves_original_records_and_source_packet_fingerprints():
    provider = Provider()
    provider.review["wording_valid"] = True
    saved = await run_cases([case()], executor(provider), metadata={})
    packets = review_packets([case()], saved)
    row = saved["cases"][0]
    row["diagnostics"]["schema_version"] = "director-diagnostics.v1"
    row["diagnostics_hash"] = content_hash(row["diagnostics"])
    for attempt in row["attempts"]:
        attempt.pop("raw_output_json_sha256")
    original = copy.deepcopy(saved)
    assert review_packets([case()], saved) == packets

    class Grader:
        async def __call__(self, rubric, candidate):
            from async_grader import Judgment

            return Judgment("accept")

    rejudged = await rejudge_cases([case()], saved, Grader(), metadata={})
    assert saved == original
    assert rejudged["cases"][0]["diagnostics"] == row["diagnostics"]
    assert rejudged["cases"][0]["diagnostics_hash"] == row["diagnostics_hash"]
    assert rejudged["cases"][0]["attempts"] == row["attempts"]


async def test_legacy_v1_does_not_claim_new_response_content_binding():
    provider = Provider()
    provider.review["wording_valid"] = True
    saved = await run_cases([case()], executor(provider), metadata={})
    row = saved["cases"][0]
    packets = review_packets([case()], saved)
    row["diagnostics"]["schema_version"] = "director-diagnostics.v1"
    row["diagnostics"]["reviews"][0]["assessment"]["reason_summary"] = "legacy changed reason"
    row["diagnostics_hash"] = content_hash(row["diagnostics"])
    for attempt in row["attempts"]:
        attempt.pop("raw_output_json_sha256")
    # v1은 원래 보증만 유지한다. 이 반례를 v2 수준으로 검증했다고 보고하지 않는다.
    assert review_packets([case()], saved) == packets


async def test_trajectory_success_and_failure_preserve_diagnostics_and_hash():
    for rejected in (False, True):
        provider = Provider()
        provider.review["wording_valid"] = not rejected
        state = {"status": "ready", "scope": {}, "executions": []}
        await _execute(state, executor(provider), "director", payload())
        event = state["executions"][0]
        assert event.get("diagnostics") is not None
        assert event["diagnostics_hash"] == content_hash(event["diagnostics"])
        assert event["status"] == ("failed" if rejected else "succeeded")


async def test_cancelled_service_preserves_partial_source_without_validated_review():
    checkpoints = []

    async def checkpoint(value):
        checkpoints.append(copy.deepcopy(value))

    with pytest.raises(asyncio.CancelledError):
        await run_cases(
            [case()],
            executor(Provider(failure=asyncio.CancelledError())),
            metadata={},
            checkpoint=checkpoint,
        )
    inflight = checkpoints[-1]["inflight_case"]
    assert inflight.get("source_snapshot") is not None
    assert len(inflight["source_snapshot"]["requests"]) == 2
    assert len(inflight["attempts"]) == 1
    assert inflight.get("diagnostics") is None


async def test_validated_review_must_match_response_json_types_before_capture():
    class WrongRawProvider(Provider):
        async def __call__(self, request, validator):
            result = await super().__call__(request, validator)
            if request.payload["operation"] == "review":
                raw = {**self.review, "plan_valid": 1}
                return replace(
                    result,
                    attempts=(
                        replace(result.attempts[0], raw_output=json.dumps(raw, ensure_ascii=False)),
                    ),
                )
            return result

    with pytest.raises(ExecutionError) as caught:
        await executor(WrongRawProvider())("question", payload())
    assert getattr(caught.value, "diagnostics", None) is None


async def test_trajectory_cancellation_checkpoints_partial_event_and_sources():
    from director_cases import build_cohort

    from scripts.director_trajectory import advance, create_trajectory

    checkpoints = []

    async def checkpoint(value):
        checkpoints.append(value)

    state = create_trajectory(build_cohort().select("pilot")[0], session_id="cancel")
    # 실제 첫 질문의 평가 키·참조 선택은 기존 trajectory fixture가 수행한다.
    from tests.test_director_trajectory import Provider as TrajectoryProvider
    from tests.test_director_trajectory import executor as trajectory_executor

    class CancelProvider(TrajectoryProvider):
        async def __call__(self, request, validator):
            if request.payload.get("operation") == "review":
                raise asyncio.CancelledError()
            return await super().__call__(request, validator)

    with pytest.raises(asyncio.CancelledError):
        await advance(state, trajectory_executor(CancelProvider()), checkpoint=checkpoint)
    event = checkpoints[-1]["executions"][0]
    assert checkpoints[-1]["status"] == "interrupted"
    assert event["status"] == "interrupted"
    assert len(event["source_snapshot"]["requests"]) == 2
    assert len(event["attempts"]) == 1


async def test_judge_cancellation_keeps_successful_review_diagnostics_inflight():
    provider = Provider()
    provider.review["wording_valid"] = True
    checkpoints = []

    async def checkpoint(value):
        checkpoints.append(value)

    async def cancel_grader(rubric, candidate):
        raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        await run_cases(
            [case()],
            executor(provider),
            metadata={},
            grader=cancel_grader,
            diagnostic_judge=True,
            checkpoint=checkpoint,
        )
    row = checkpoints[-1]["inflight_case"]
    assert row["service_status"] == "completed"
    assert row["diagnostics_hash"] == content_hash(row["diagnostics"])
    assert len(row["attempts"]) == 2
    assert row["output"]["question"] is not None


async def test_rejudge_cancellation_preserves_original_diagnostics_and_output_inflight():
    provider = Provider()
    provider.review["wording_valid"] = True
    saved = await run_cases([case()], executor(provider), metadata={})
    checkpoints = []

    async def checkpoint(value):
        checkpoints.append(value)

    async def cancel_grader(rubric, candidate):
        raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        await rejudge_cases([case()], saved, cancel_grader, metadata={}, checkpoint=checkpoint)
    inflight = checkpoints[-1].get("inflight_case")
    assert inflight is not None
    original = saved["cases"][0]
    assert inflight["diagnostics"] == original["diagnostics"]
    assert inflight["diagnostics_hash"] == original["diagnostics_hash"]
    assert inflight["output"] == original["output"]
    assert inflight["attempts"] == original["attempts"]


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
