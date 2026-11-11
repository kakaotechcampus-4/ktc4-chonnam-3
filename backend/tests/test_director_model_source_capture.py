"""원래 사례가 아니라 실제 Plan/Review에 전달한 모델 입력을 보존한다."""

import hashlib
import json
from dataclasses import asdict

import pytest
from async_grader import content_hash
from devon_ai import contracts as c
from director_sources import source_context

from scripts.ai_eval_bridge import ServiceExecutor
from tests.test_ai_eval_bridge import contract, payload


@pytest.mark.parametrize("version", ["director_v8", "director_v9"])
async def test_director_execution_captures_exact_model_inputs_with_projection_boundary(version):
    seen = []

    async def invoke(request, validate):
        seen.append(request)
        raw = (
            {
                "question": {
                    "persona": "hr_manager",
                    "text": "맡은 역할은 무엇인가요?",
                    "topic_code": "role",
                    "question_contract": asdict(contract()),
                    "evidence_refs": [],
                    "jd_requirement_ids": [],
                    "question_type": "main",
                    "parent_turn_id": None,
                },
                "intent": "역할 확인",
                "reason_summary": "첫 질문",
            }
            if request.payload["operation"] == "plan"
            else {
                "plan_valid": True,
                "context_valid": True,
                "wording_valid": True,
                "contract_matches": True,
                "safe_alternative": True,
                "reason_summary": "원문과 일치",
            }
        )
        attempt = c.AttemptMetadata(
            len(seen), "fixture", "fixture-model", version, request.schema_version, 1, 2, 3
        )
        return c.ModelResult(
            validate(json.loads(json.dumps(raw, ensure_ascii=False))), None, (attempt,)
        )

    supplied = payload()
    supplied["service_input"]["reference_texts"] = [
        {
            "kind": "job_posting",
            "id": "posting",
            "text": json.dumps(
                {"raw_text": "API 서비스 개발", "_fetch_trace": "HIDDEN_METADATA"},
                ensure_ascii=False,
            ),
        }
    ]
    runner = ServiceExecutor(
        {"director": c.PromptSpec("director", version, "fixture-model", "fixture")},
        c.CallLimits(5, 1024, 65536, 65536),
        lambda: invoke,
    )
    result = await runner("question", supplied)
    snapshot = result.source_snapshot
    assert snapshot is not None
    assert snapshot["schema_version"] == "director-model-sources.v3"
    assert snapshot["service_input_sha256"] == content_hash(supplied)
    assert [item["operation"] for item in snapshot["requests"]] == ["plan", "review"]
    for actual, captured in zip(seen, snapshot["requests"], strict=True):
        assert captured["payload"] == json.loads(json.dumps(actual.payload, ensure_ascii=False))
        assert captured["payload_sha256"] == content_hash(captured["payload"])
        assert captured["prompt_template"] == actual.prompt.template
        assert (
            captured["prompt_template_sha256"]
            == hashlib.sha256(actual.prompt.template.encode("utf-8")).hexdigest()
        )
    materials = source_context(snapshot)["source"]["materials"]
    shared = next(item for item in materials if item["source_kind"] == "director_shared_payload")
    common = json.loads(shared["content"])
    visible = [item for item in materials if item["source_kind"] == "director_model_request"]
    for captured, item in zip(snapshot["requests"], visible, strict=True):
        value = json.loads(item["content"])
        assert value["shared_payload_ref"] == shared["id"]
        assert content_hash({**common, **value["payload_delta"]}) == captured["payload_sha256"]
    assert ("HIDDEN_METADATA" in json.dumps(snapshot)) == (version == "director_v8")


async def test_failed_review_keeps_actual_model_sources_for_audit():
    from eval_runner import ExecutionError

    async def invoke(request, validate):
        attempt = c.AttemptMetadata(
            1, "fixture", "fixture-model", "director_v9", request.schema_version, 1, 2, 3
        )
        if request.payload["operation"] == "review":
            return c.ModelResult(
                None, c.CallFailure("provider", "llm_failed", "fixture"), (attempt,)
            )
        raw = {
            "question": {
                "persona": "hr_manager",
                "text": "역할을 소개해 주세요.",
                "topic_code": "role",
                "question_contract": json.loads(json.dumps(asdict(contract()))),
                "evidence_refs": [],
                "jd_requirement_ids": [],
                "question_type": "main",
                "parent_turn_id": None,
            },
            "intent": "역할 확인",
            "reason_summary": "첫 질문",
        }
        return c.ModelResult(validate(raw), None, (attempt,))

    runner = ServiceExecutor(
        {"director": c.PromptSpec("director", "director_v9", "fixture-model", "fixture")},
        c.CallLimits(5, 1024, 65536, 65536),
        lambda: invoke,
    )
    with pytest.raises(ExecutionError) as caught:
        await runner("question", payload())
    assert [item["operation"] for item in caught.value.source_snapshot["requests"]] == [
        "plan",
        "review",
    ]
    assert caught.value.source_snapshot["service_input_sha256"] == content_hash(payload())
