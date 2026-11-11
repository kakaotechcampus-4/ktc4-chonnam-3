"""새 사적 Plan 원문과 실제 Review 입력의 구성 질문이 결합되어야 한다."""

import copy
import hashlib
import json

import pytest
from async_grader import content_hash
from devon_ai import contracts as c
from director_diagnostics import validate_diagnostics
from director_sources import validate_snapshot
from eval_runner import ExecutionError, run_cases

from scripts.ai_eval_bridge import ServiceExecutor, _attempts
from tests.test_director_review_diagnostics import case


class SourceBoundProvider:
    def __init__(self, *, rejected=False, corrupt_raw=False):
        self.rejected = rejected
        self.corrupt_raw = corrupt_raw
        self.requests = []
        self.raws = []

    async def __call__(self, request, validator):
        self.requests.append(request)
        raw = (
            {
                "question": {
                    "persona": "hr_manager",
                    "preamble": "",
                    "request": "맡은 역할은 무엇인가요?",
                    "topic_code": "role",
                    "question_contract": {
                        "point_key": "role",
                        "assumptions": [],
                        "basis_refs": [],
                        "evaluation_keys": [],
                    },
                    "evidence_refs": [],
                    "jd_requirement_ids": [],
                    "question_type": "main",
                    "parent_turn_id": None,
                },
                "intent": "역할 확인",
                "reason_summary": "현재 자료의 범위",
            }
            if request.payload["operation"] == "plan"
            else {
                "plan_valid": True,
                "context_valid": True,
                "wording_valid": not self.rejected,
                "contract_matches": True,
                "safe_alternative": True,
                "reason_summary": "문장 검토",
                "point_coverage": [
                    {
                        "key": "role",
                        "status": "asked",
                        "question_excerpt": "맡은 역할은 무엇인가요?",
                    }
                ],
            }
        )
        checked = validator(copy.deepcopy(raw))
        if self.corrupt_raw and request.payload["operation"] == "plan":
            if self.corrupt_raw == "request":
                raw["question"]["request"] = "다른 역할은 무엇인가요?"
            else:
                raw[self.corrupt_raw] = "검증한 원문과 다른 설명"
        text = json.dumps(raw, ensure_ascii=False)
        self.raws.append(text)
        attempt = c.AttemptMetadata(
            len(self.requests),
            "fixture",
            "fixture-model",
            request.prompt.version,
            request.schema_version,
            1,
            2,
            3,
            raw_output=text,
        )
        return c.ModelResult(checked, None, (attempt,))


def executor(provider):
    return ServiceExecutor(
        {
            "director": c.PromptSpec(
                "director",
                "director_v17@fixture",
                "fixture-model",
                "## 공통\n근거\n## 질문 생성\n요청\n## 독립 검토\n전체 문장 검토",
            )
        },
        c.CallLimits(5, 1024, 65536, 65536),
        lambda: provider,
    )


@pytest.mark.parametrize("rejected", [False, True])
async def test_v17_plan_raw_binds_canonical_question_and_preserves_v3_source_shape(rejected):
    provider = SourceBoundProvider(rejected=rejected)
    current = case()
    saved = await run_cases([current], executor(provider), metadata={})
    row = saved["cases"][0]
    assert row["status"] == ("failed" if rejected else "succeeded")
    assert [request.schema_version for request in provider.requests] == [
        "director-plan.v4",
        "director-review.v3",
    ]
    snapshot = validate_snapshot(row["source_snapshot"])
    assert snapshot["schema_version"] == "director-model-sources.v3"
    assert set(snapshot) == {"schema_version", "service_input_sha256", "requests"}
    question = snapshot["requests"][1]["payload"]["question"]
    assert (
        question["text"] == question["question_contract"]["purpose"] == ("맡은 역할은 무엇인가요?")
    )
    assert question["question_contract"]["required_points"] == [
        {"key": "role", "description": "맡은 역할은 무엇인가요?"}
    ]
    plan = row["attempts"][0]
    assert plan["canonical_question_sha256"] == content_hash(question)
    assert plan["raw_output_sha256"] == hashlib.sha256(provider.raws[0].encode()).hexdigest()
    assert "raw_output" not in plan
    assert (
        validate_diagnostics(
            row["diagnostics"],
            service_input_sha256=content_hash(current.payload),
            source_snapshot=snapshot,
            attempts=row["attempts"],
        )
        == row["diagnostics"]
    )


@pytest.mark.parametrize("change", ["missing", "digest", "version", "legacy_family", "question"])
async def test_v17_diagnostics_rejects_rehashed_plan_question_binding_changes(change):
    saved = await run_cases([case()], executor(SourceBoundProvider()), metadata={})
    row = saved["cases"][0]
    snapshot = row["source_snapshot"]
    if change == "missing":
        row["attempts"][0].pop("canonical_question_sha256")
    elif change == "digest":
        row["attempts"][0]["canonical_question_sha256"] = "0" * 64
    elif change == "version":
        snapshot["requests"][0]["schema_version"] = "director-plan.v3"
        row["attempts"][0]["schema_version"] = "director-plan.v3"
    elif change == "legacy_family":
        for request, attempt in zip(snapshot["requests"], row["attempts"], strict=True):
            request["prompt_version"] = attempt["prompt_version"] = "director_v16@fixture"
        snapshot["requests"][0]["schema_version"] = "director-plan.v3"
        row["attempts"][0]["schema_version"] = "director-plan.v3"
        row["diagnostics"]["reviews"][0]["prompt_version"] = "director_v16@fixture"
    else:
        question = snapshot["requests"][1]["payload"]["question"]
        question["text"] = "다른 역할은 무엇인가요?"
        question["question_contract"]["purpose"] = question["text"]
        question["question_contract"]["required_points"][0]["description"] = question["text"]
        snapshot["requests"][1]["payload_sha256"] = content_hash(snapshot["requests"][1]["payload"])
        row["diagnostics"]["reviews"][0]["request_payload_sha256"] = snapshot["requests"][1][
            "payload_sha256"
        ]
    row["diagnostics"]["source_snapshot_sha256"] = content_hash(snapshot)
    with pytest.raises(ValueError, match="diagnostic|snapshot|Plan"):
        validate_diagnostics(
            row["diagnostics"],
            service_input_sha256=content_hash(case().payload),
            source_snapshot=snapshot,
            attempts=row["attempts"],
        )


@pytest.mark.parametrize("change", ["request", "intent", "reason_summary", "extra"])
async def test_v17_raw_different_from_the_validated_plan_never_starts_review(change):
    provider = SourceBoundProvider(corrupt_raw=change)
    with pytest.raises(ExecutionError, match="director_plan_binding_invalid"):
        await executor(provider)("question", case().payload)
    assert len(provider.requests) == 1


def test_legacy_attempt_summaries_do_not_gain_a_source_bound_question_field():
    attempt = c.AttemptMetadata(
        1,
        "fixture",
        "model",
        "director_v16",
        "director-plan.v3",
        1,
        2,
        3,
        raw_output='{"question":{}}',
    )
    assert "canonical_question_sha256" not in _attempts([attempt])[0]
