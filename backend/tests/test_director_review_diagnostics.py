"""검증된 Review 진단만 실제 요청·응답 지문과 함께 보존한다."""

import asyncio
import copy
import hashlib
import json
from dataclasses import asdict, replace

import pytest
from async_grader import content_hash
from devon_ai import contracts as c
from director_diagnostics import validate_diagnostics
from eval_cases import Case
from eval_runner import ExecutionError, rejudge_cases, review_packets, run_cases

from scripts.ai_eval_bridge import ServiceExecutor, _attempts
from scripts.director_trajectory import _execute
from tests.test_ai_eval_bridge import contract, payload


class Provider:
    def __init__(self, review=None, failure=None, *, question_contract=None):
        self.review = review or {
            "plan_valid": True,
            "context_valid": True,
            "wording_valid": False,
            "contract_matches": True,
            "safe_alternative": True,
            "reason_summary": "PRIVATE_REVIEW 표현이 복합적입니다.",
        }
        self.failure = failure
        self.question_contract = question_contract or contract()
        self.requests = []
        self.raws = []

    async def __call__(self, request, validator):
        self.requests.append(request)
        raw = (
            {
                "question": {
                    "persona": "hr_manager",
                    "text": "맡은 역할은 무엇인가요?",
                    "topic_code": "role",
                    "question_contract": asdict(self.question_contract),
                    "evidence_refs": [],
                    "jd_requirement_ids": [],
                },
                "intent": "역할 확인",
                "reason_summary": "첫 질문",
            }
            if request.payload["operation"] == "plan"
            else self.review
        )
        raw_text = json.dumps(raw, ensure_ascii=False)
        self.raws.append(raw_text)
        attempt = c.AttemptMetadata(
            len(self.requests),
            "fixture",
            "fixture-model",
            request.prompt.version,
            request.schema_version,
            1,
            2,
            3,
            raw_output=raw_text,
        )
        try:
            checked = validator(json.loads(raw_text))
        except c.ContractError as error:
            return c.ModelResult(None, c.CallFailure(error.stage, "invalid", "private"), (attempt,))
        if self.failure and request.payload["operation"] == "review":
            raise self.failure
        return c.ModelResult(checked, None, (attempt,))


def executor(provider, *, point_review=False, stable_review=False):
    prompt = (
        c.PromptSpec(
            "director",
            "director_v16@fixture" if stable_review else "director_v14@fixture",
            "fixture-model",
            "## 공통\n공통 지침\n## 질문 생성\n질문 지침\n## 독립 검토\n검토 지침",
        )
        if point_review
        else c.PromptSpec("director", "director_v2", "fixture-model", "fixture")
    )
    return ServiceExecutor(
        {"director": prompt},
        c.CallLimits(5, 1024, 65536, 65536),
        lambda: provider,
    )


def case():
    return Case(
        "diagnostic",
        1,
        "question",
        "dev",
        "diagnostic-group",
        payload(),
        {
            "allowed": [],
            "forbidden": [],
            "grader_controls": [],
            "review": {"status": "unreviewed", "reviewer": None},
        },
    )


async def failed_execution():
    provider = Provider()
    with pytest.raises(ExecutionError) as caught:
        await executor(provider)("question", payload())
    return provider, caught.value


async def test_rejected_review_has_validated_flags_reason_recovery_and_exact_binding():
    provider, error = await failed_execution()
    diagnostics = getattr(error, "diagnostics", None)
    assert diagnostics is not None
    assert diagnostics["schema_version"] == "director-diagnostics.v2"
    assert diagnostics["service_input_sha256"] == content_hash(payload())
    assert diagnostics["source_snapshot_sha256"] == content_hash(error.source_snapshot)
    review = diagnostics["reviews"][0]
    assert review["assessment"] == provider.review
    assert review["recovery"] == "rewrite"
    assert review["response_raw_sha256"] == hashlib.sha256(provider.raws[1].encode()).hexdigest()
    assert review["request_payload_sha256"] == content_hash(provider.requests[1].payload)
    assert review["prompt_version"] == "director_v2"
    assert review["prompt_template_sha256"] == hashlib.sha256(b"fixture").hexdigest()
    assert "raw_output" not in json.dumps(diagnostics)
    assert error.code == "director_candidate_rewrite"


def point_review_provider(*, asked):
    point = c.RequiredPoint("role", "맡은 역할" if asked else "맡은 역할과 그 역할을 선택한 이유")
    provider = Provider(question_contract=replace(contract(), required_points=(point,)))
    provider.review.update(
        wording_valid=True,
        point_coverage={
            point.key: {
                "status": "asked" if asked else "not_asked",
                "question_excerpt": "맡은 역할은 무엇인가요?" if asked else None,
            }
        },
    )
    return provider


@pytest.mark.parametrize("asked", [False, True])
async def test_point_review_binds_raw_receipt_and_effective_decision(asked):
    provider = point_review_provider(asked=asked)
    current_case = case()
    saved = await run_cases([current_case], executor(provider, point_review=True), metadata={})
    row = saved["cases"][0]
    assert [request.schema_version for request in provider.requests] == [
        "director-plan.v3",
        "director-review.v2",
    ]
    assert row["status"] == ("succeeded" if asked else "failed")
    assert row.get("error_code") == (None if asked else "director_candidate_rewrite")
    assert row["diagnostics"]["schema_version"] == "director-diagnostics.v2"
    review = row["diagnostics"]["reviews"][0]
    assert review["assessment"] == provider.review
    assert review["assessment"]["contract_matches"] is True
    assert review["recovery"] == (None if asked else "rewrite")
    assert review["response_raw_sha256"] == hashlib.sha256(provider.raws[1].encode()).hexdigest()
    assert row["attempts"][1]["raw_output_json_sha256"] == content_hash(provider.review)
    assert "PRIVATE_REVIEW" not in json.dumps(review_packets([current_case], saved))


@pytest.mark.parametrize("asked", [False, True])
async def test_stable_point_review_binds_exact_array_receipt_and_effective_decision(asked):
    provider = point_review_provider(asked=asked)
    provider.review["point_coverage"] = [
        {"key": key, **entry} for key, entry in provider.review["point_coverage"].items()
    ]
    current_case = case()
    saved = await run_cases(
        [current_case], executor(provider, point_review=True, stable_review=True), metadata={}
    )
    row = saved["cases"][0]
    assert row["status"] == ("succeeded" if asked else "failed")
    assert provider.requests[-1].schema_version == "director-review.v3"
    receipt = row["diagnostics"]["reviews"][0]
    assert receipt["assessment"] == provider.review
    assert receipt["recovery"] == (None if asked else "rewrite")
    assert row["attempts"][1]["raw_output_json_sha256"] == content_hash(provider.review)
    assert (
        validate_diagnostics(
            row["diagnostics"],
            service_input_sha256=content_hash(current_case.payload),
            source_snapshot=row["source_snapshot"],
            attempts=row["attempts"],
        )
        == row["diagnostics"]
    )
    assert len(review_packets([current_case], saved)) == int(asked)


@pytest.mark.parametrize("corruption", ["duplicate", "missing", "unknown", "excerpt", "downgrade"])
async def test_stable_point_review_rejects_rehashed_array_tampering(corruption):
    provider = point_review_provider(asked=False)
    provider.review["point_coverage"] = [
        {"key": key, **entry} for key, entry in provider.review["point_coverage"].items()
    ]
    current_case = case()
    saved = await run_cases(
        [current_case], executor(provider, point_review=True, stable_review=True), metadata={}
    )
    row = saved["cases"][0]
    receipt = row["diagnostics"]["reviews"][0]
    entries = receipt["assessment"]["point_coverage"]
    if corruption == "duplicate":
        entries.append(copy.deepcopy(entries[0]))
    elif corruption == "missing":
        entries.clear()
    elif corruption == "unknown":
        entries[0]["key"] = "other"
    elif corruption == "excerpt":
        entries[0].update(status="asked", question_excerpt="선택한 이유")
    else:
        row["source_snapshot"]["requests"][1]["schema_version"] = "director-review.v2"
        row["attempts"][1]["schema_version"] = "director-review.v2"
        row["source_snapshot_hash"] = content_hash(row["source_snapshot"])
        row["diagnostics"]["source_snapshot_sha256"] = row["source_snapshot_hash"]
    row["attempts"][1]["raw_output_json_sha256"] = content_hash(receipt["assessment"])
    row["diagnostics_hash"] = content_hash(row["diagnostics"])
    with pytest.raises(ValueError, match="diagnostic"):
        review_packets([current_case], saved)


@pytest.mark.parametrize(
    "corruption", ["assessment", "excerpt", "recovery", "legacy_downgrade", "wire_downgrade"]
)
async def test_point_review_rejects_rehashed_tampering_and_downgrades(corruption):
    current_case = case()
    provider = point_review_provider(asked=False)
    saved = await run_cases([current_case], executor(provider, point_review=True), metadata={})
    row = saved["cases"][0]
    diagnostics = row["diagnostics"]
    review = diagnostics["reviews"][0]
    attempt = row["attempts"][1]
    if corruption == "assessment":
        review["assessment"]["point_coverage"]["role"] = {
            "status": "asked",
            "question_excerpt": "맡은 역할은 무엇인가요?",
        }
        review["recovery"] = None
    elif corruption == "excerpt":
        # 내용 지문이 서로 맞아도 질문 밖의 구절은 확인점 근거가 될 수 없다.
        review["assessment"]["point_coverage"]["role"]["question_excerpt"] = "선택한 이유"
        attempt["raw_output_json_sha256"] = content_hash(review["assessment"])
    elif corruption == "recovery":
        review["recovery"] = None
    elif corruption == "legacy_downgrade":
        diagnostics["schema_version"] = "director-diagnostics.v1"
        del attempt["raw_output_json_sha256"]
    else:
        row["source_snapshot"]["requests"][1]["schema_version"] = "director-review.v1"
        attempt["schema_version"] = "director-review.v1"
        row["source_snapshot_hash"] = content_hash(row["source_snapshot"])
        diagnostics["source_snapshot_sha256"] = row["source_snapshot_hash"]
    row["diagnostics_hash"] = content_hash(diagnostics)
    with pytest.raises(ValueError, match="diagnostic"):
        review_packets([current_case], saved)


@pytest.mark.parametrize(
    "check,recovery",
    [
        ("plan_valid", "replan"),
        ("context_valid", "replan"),
        ("safe_alternative", "no_valid_candidate"),
        ("contract_matches", "rewrite"),
    ],
)
async def test_review_diagnostics_preserves_actual_recovery_selection(check, recovery):
    provider = Provider()
    provider.review[check] = False
    with pytest.raises(ExecutionError) as caught:
        await executor(provider)("question", payload())
    assert getattr(caught.value, "diagnostics", {})["reviews"][0]["recovery"] == recovery


@pytest.mark.parametrize("corruption", ["partial", "boolean", "extra", "empty_reason"])
async def test_unvalidated_review_is_never_recorded_as_diagnostics(corruption):
    provider = Provider()
    if corruption == "partial":
        del provider.review["plan_valid"]
    elif corruption == "boolean":
        provider.review["plan_valid"] = 1
    elif corruption == "extra":
        provider.review["api_key"] = "PRIVATE_KEY"
    else:
        provider.review["reason_summary"] = " "
    with pytest.raises(ExecutionError) as caught:
        await executor(provider)("question", payload())
    assert getattr(caught.value, "diagnostics", None) is None


async def test_successful_diagnostics_stay_out_of_judge_packets_and_survive_rejudge():
    provider = Provider()
    provider.review["wording_valid"] = True
    saved = await run_cases([case()], executor(provider), metadata={})
    row = saved["cases"][0]
    assert row.get("diagnostics") is not None
    assert row["diagnostics_hash"] == content_hash(row["diagnostics"])
    assert row["diagnostics"]["reviews"][0]["recovery"] is None
    assert "PRIVATE_REVIEW" not in json.dumps(review_packets([case()], saved))

    class Grader:
        async def __call__(self, rubric, candidate):
            from async_grader import Judgment

            return Judgment("accept")

        async def judge_with_context(self, rubric, candidate, source_context):
            assert "PRIVATE_REVIEW" not in str((candidate, source_context))
            return await self(rubric, candidate)

    rejudged = await rejudge_cases([case()], saved, Grader(), metadata={})
    assert rejudged["cases"][0]["diagnostics"] == row["diagnostics"]
    assert rejudged["cases"][0]["diagnostics_hash"] == row["diagnostics_hash"]
    assert rejudged["cases"][0]["judge"]["verdict"] == "accept"


@pytest.mark.parametrize(
    "corruption",
    ["body", "missing", "request", "response", "recovery", "reason_rehashed", "checks_rehashed"],
)
async def test_rejudge_rejects_changed_diagnostic_hash_or_binding(corruption):
    saved = await run_cases([case()], executor(Provider()), metadata={})
    row = saved["cases"][0]
    assert row.get("diagnostics") is not None
    if corruption == "body":
        row["diagnostics"]["reviews"][0]["assessment"]["reason_summary"] = "tampered"
    elif corruption == "missing":
        del row["diagnostics"]
    elif corruption == "request":
        row["diagnostics"]["reviews"][0]["request_payload_sha256"] = "0" * 64
        row["diagnostics_hash"] = content_hash(row["diagnostics"])
    elif corruption == "response":
        row["attempts"][1]["raw_output_sha256"] = "0" * 64
    elif corruption == "reason_rehashed":
        row["diagnostics"]["reviews"][0]["assessment"]["reason_summary"] = "changed but nonempty"
        row["diagnostics_hash"] = content_hash(row["diagnostics"])
    elif corruption == "checks_rehashed":
        row["diagnostics"]["reviews"][0]["assessment"]["wording_valid"] = True
        row["diagnostics"]["reviews"][0]["recovery"] = None
        row["diagnostics_hash"] = content_hash(row["diagnostics"])
    else:
        row["diagnostics"]["reviews"][0]["recovery"] = "replan"
        row["diagnostics_hash"] = content_hash(row["diagnostics"])
    with pytest.raises(ValueError, match="diagnostic"):
        review_packets([case()], saved)


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
