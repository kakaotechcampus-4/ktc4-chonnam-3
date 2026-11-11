"""Judge는 수집 전 입력이 아니라 실제 Director 모델 표시 범위를 읽어야 한다."""

import asyncio
import copy
import hashlib
import json

import pytest
from async_grader import content_hash
from eval_cases import Case
from eval_runner import Execution, review_packets, run_cases


def fixture():
    return Case(
        "q-snapshot",
        1,
        "question",
        "dev",
        "snapshot-group",
        {
            "service_task": "director",
            "service_input": {
                "context": {"interview_id": "session"},
                "reference_texts": [{"kind": "job_posting", "id": "jd", "text": "HIDDEN_METADATA"}],
            },
        },
        {
            "allowed": [
                {"id": "grounded", "purpose": "Only visible material supports the question."}
            ],
            "forbidden": [],
            "grader_controls": [],
            "review": {"status": "unreviewed", "reviewer": None},
        },
    )


def snapshot(case=None, text="visible raw source"):
    case = case or fixture()
    payload = {
        "operation": "plan",
        "context": {"interview_id": "session"},
        "reference_texts": [{"kind": "job_posting", "id": "jd", "text": text}],
    }
    request = {
        "operation": "plan",
        "prompt_version": "director_v9",
        "model": "fixture-model",
        "schema_version": "director-plan.v3",
        "payload": payload,
        "payload_sha256": content_hash(payload),
    }
    return {
        "schema_version": "director-model-sources.v1",
        "service_input_sha256": content_hash(case.payload),
        "requests": [request],
    }


def test_review_packet_uses_captured_model_material_not_hidden_original_fields():
    case = fixture()
    observed = snapshot(case)

    async def execute(kind, payload):
        return Execution({"question": "candidate"}, source_snapshot=observed)

    saved = asyncio.run(run_cases([case], execute, metadata={}))
    assert saved["cases"][0]["status"] == "succeeded"
    packet = review_packets([case], saved)[0]
    material = packet["source_context"]["source"]["materials"][0]["content"]
    assert "visible raw source" in material
    assert "HIDDEN_METADATA" not in str(packet["source_context"])
    assert saved["cases"][0]["source_snapshot"] == observed


def test_oversized_model_material_keeps_original_snapshot_and_unique_binding():
    from director_sources import source_context

    first, second = snapshot(text="a" * 70000), snapshot(text="b" * 70000)
    left, right = source_context(first), source_context(second)
    assert left["source_materials_provided"] is False
    assert "context_byte_limit_exceeded" in left["limitations"]
    assert left["source"]["text_hash"] == content_hash(first)
    assert content_hash(left) != content_hash(right)


def test_capture_hash_and_original_case_binding_are_both_verified():
    from director_sources import source_context

    altered = snapshot()
    altered["requests"][0]["payload"]["reference_texts"][0]["text"] = "tampered"
    with pytest.raises(ValueError, match="hash"):
        source_context(altered)

    case = fixture()
    wrong = snapshot()
    wrong["service_input_sha256"] = "0" * 64

    async def execute(kind, payload):
        return Execution({"question": "candidate"}, source_snapshot=wrong)

    saved = asyncio.run(run_cases([case], execute, metadata={}))
    assert saved["cases"][0]["status"] == "failed"
    assert saved["cases"][0]["error_code"] == "ValueError"


def policy_snapshot(text="company_job_fit은 실제 JD 요구와 프로젝트 경험의 연결을 묻는다."):
    observed = snapshot()
    observed["schema_version"] = "director-model-sources.v2"
    request = observed["requests"][0]
    request["prompt_template"] = text
    request["prompt_template_sha256"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
    review = copy.deepcopy(request)
    review["operation"] = "review"
    review["payload"]["operation"] = "review"
    review["payload_sha256"] = content_hash(review["payload"])
    observed["requests"].append(review)
    return observed


def test_v1_judge_context_binding_is_unchanged_by_policy_snapshot_support():
    from director_sources import source_context

    assert content_hash(source_context(snapshot())) == (
        "8878fd3b36c2aef6623ed1e65c7d14b49f38ea554ae158f9d9ded2fbee4e2056"
    )


def test_v2_exports_exact_policy_once_and_links_each_actual_request_to_it():
    from director_sources import source_context

    observed = policy_snapshot()
    context = source_context(observed)
    materials = context["source"]["materials"]
    policies = [item for item in materials if item["source_kind"] == "director_prompt_policy"]
    assert len(policies) == 1
    assert policies[0]["content"] == observed["requests"][0]["prompt_template"]
    assert policies[0]["source_field"] == "PromptSpec.template"
    assert policies[0]["text_hash"] == observed["requests"][0]["prompt_template_sha256"]
    requests = [item for item in materials if item["source_kind"] == "director_model_request"]
    assert len(requests) == 2
    for request in requests:
        value = json.loads(request["content"])
        assert value["prompt_template_sha256"] == policies[0]["text_hash"]
        assert "prompt_template" not in value


@pytest.mark.parametrize("corruption", ["body", "hash", "missing"])
def test_v2_rejects_missing_or_tampered_policy(corruption):
    from director_sources import source_context

    observed = policy_snapshot()
    if corruption == "body":
        observed["requests"][0]["prompt_template"] = "다른 정책"
    elif corruption == "hash":
        observed["requests"][0]["prompt_template_sha256"] = "0" * 64
    else:
        del observed["requests"][0]["prompt_template"]
    with pytest.raises(ValueError):
        source_context(observed)


def test_v2_policy_budget_overflow_preserves_snapshot_identity_and_limit():
    from director_sources import source_context

    observed = policy_snapshot("정책원문" * 20000)
    context = source_context(observed)
    assert context["source_materials_provided"] is False
    assert "context_byte_limit_exceeded" in context["limitations"]
    assert context["source"]["text_hash"] == content_hash(observed)


def test_v2_runner_packet_preserves_policy_and_new_follow_up_fields():
    from director_sources import source_context

    case = fixture()
    observed = policy_snapshot()
    for request in observed["requests"]:
        request["payload"]["context"]["follow_up_options"] = [
            {"missing_point_keys": ["failure"], "evaluation_keys": ["project_understanding"]}
        ]
        request["payload"]["context"]["presented_evaluation_keys"] = ["contribution_clarity"]
        request["payload_sha256"] = content_hash(request["payload"])

    async def execute(kind, payload):
        return Execution({"question": "candidate"}, source_snapshot=observed)

    result = asyncio.run(run_cases([case], execute, metadata={}))
    assert result["cases"][0]["status"] == "succeeded"
    packet = review_packets([case], result)[0]
    assert packet["binding"]["source_context_sha256"] == content_hash(source_context(observed))
    requests = [
        item
        for item in packet["source_context"]["source"]["materials"]
        if item["source_kind"] == "director_model_request"
    ]
    shown = json.loads(requests[0]["content"])["payload"]["context"]
    assert shown["follow_up_options"][0]["missing_point_keys"] == ["failure"]
    assert shown["presented_evaluation_keys"] == ["contribution_clarity"]


def test_v2_judge_context_binding_remains_unchanged():
    from director_sources import source_context

    assert content_hash(source_context(policy_snapshot())) == (
        "3ea7f901550320c688e95c1d77308973dd1cb031a4e8afbfba2444a4c77e91b1"
    )


def shared_payload_snapshot():
    observed = policy_snapshot()
    observed["schema_version"] = "director-model-sources.v3"
    for request in observed["requests"]:
        request["payload"]["context"]["evidence"] = [
            {"evidence_id": "code", "content": "정적 코드 원문\n" * 2400}
        ]
        request["payload_sha256"] = content_hash(request["payload"])
    observed["requests"][1]["payload"]["question"] = {"text": "실패 경로는?"}
    observed["requests"][1]["payload_sha256"] = content_hash(observed["requests"][1]["payload"])
    return observed


def test_v3_preserves_real_style_shared_sources_within_judge_budget():
    from director_sources import source_context

    observed = shared_payload_snapshot()
    original = copy.deepcopy(observed)
    legacy = copy.deepcopy(observed)
    legacy["schema_version"] = "director-model-sources.v2"
    assert source_context(legacy)["source_materials_provided"] is False

    context = source_context(observed)
    assert context["source_materials_provided"] is True
    assert context["status"] == "available"
    assert "context_byte_limit_exceeded" not in context["limitations"]
    assert len(json.dumps(context, ensure_ascii=False).encode("utf-8")) <= 65536
    assert observed == original
    materials = context["source"]["materials"]
    shared = next(m for m in materials if m["source_kind"] == "director_shared_payload")
    common = json.loads(shared["content"])
    assert common["context"]["evidence"][0]["content"] == "정적 코드 원문\n" * 2400
    requests = [m for m in materials if m["source_kind"] == "director_model_request"]
    for actual, material in zip(original["requests"], requests, strict=True):
        visible = json.loads(material["content"])
        assert visible["shared_payload_ref"] == shared["id"]
        reconstructed = {**common, **visible["payload_delta"]}
        assert content_hash(reconstructed) == actual["payload_sha256"]
        assert reconstructed == actual["payload"]
        assert visible["payload_sha256"] == actual["payload_sha256"]
        assert visible["prompt_version"] == actual["prompt_version"]
        assert visible["prompt_template_sha256"] == actual["prompt_template_sha256"]


@pytest.mark.parametrize("left,right", [(True, 1), ({"enabled": True}, {"enabled": 1})])
def test_v3_does_not_share_canonically_different_conditions(left, right):
    from director_sources import source_context

    observed = policy_snapshot()
    observed["schema_version"] = "director-model-sources.v3"
    for request, value in zip(observed["requests"], (left, right), strict=True):
        request["payload"]["condition"] = value
        request["payload_sha256"] = content_hash(request["payload"])
    materials = source_context(observed)["source"]["materials"]
    shared = next(m for m in materials if m["source_kind"] == "director_shared_payload")
    common = json.loads(shared["content"])
    assert "condition" not in common
    requests = [m for m in materials if m["source_kind"] == "director_model_request"]
    for actual, material in zip(observed["requests"], requests, strict=True):
        visible = json.loads(material["content"])
        reconstructed = {**common, **visible["payload_delta"]}
        assert content_hash(reconstructed) == actual["payload_sha256"]
