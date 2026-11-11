"""평가 입력에서도 과거 계약·답변·분석과 복구 이력을 실제 경계로 검증한다."""

import copy
import json
from dataclasses import asdict

import pytest
from devon_ai import contracts as c
from devon_ai.agents.director.runtime import _feedback_payload, _input_payload
from director_cases import build_cohort
from eval_runner import ExecutionError

from scripts.ai_eval_bridge import ServiceExecutor, prepare


def base():
    case = next(item for item in build_cohort().cases if item.case_id == "dq-01-partial")
    return copy.deepcopy(case.payload)


def prior_record(value):
    turn = value["service_input"]["context"]["history"][0]
    evidence = value["service_input"]["context"]["evidence"][0]["evidence_id"]
    return {
        "question_contract": {
            "purpose": "본인이 설명한 역할 범위를 확인한다.",
            "required_points": [{"key": "role", "description": "직접 맡았다고 설명한 범위"}],
            "assumptions": [],
            "basis_refs": [],
            "evaluation_scope": "명시한 역할 설명만 확인한다.",
            "evaluation_keys": ["contribution_clarity", "communication"],
        },
        "analysis": {
            "evaluation_status": "evaluated",
            "sufficiency": "sufficient",
            "covered_points": [{"key": "role", "answer_quotes": [turn["answer"]]}],
            "missing_points": [],
            "technical_assessment": {
                "explanation": "역할 진술은 수행의 독립 증명이 아니다.",
                "answer_quotes": [],
                "evidence_refs": [evidence],
                "limitations": ["합성 진술이며 실제 기여는 검증하지 않았다."],
            },
            "contribution_scope": {"scope": "unknown", "answer_quotes": []},
            "claim_checks": [],
            "needs_verification": False,
            "verification_requests": [],
            "limitations": ["합성 진술이며 실제 기여는 검증하지 않았다."],
            "external_queries": [],
        },
    }


def expanded():
    value = base()
    turn_id = value["service_input"]["context"]["history"][0]["turn_id"]
    value["service_input"]["prior_analyses"] = {turn_id: prior_record(value)}
    value["service_input"]["recovery_feedback"] = {
        "version": "director-recovery.v1",
        "previous_candidate": copy.deepcopy(value["service_input"]["question"]),
        "recovery": "replan",
        "review_reason_summary": "기존 답변과 다른 확인 목적이 필요하다.",
    }
    return value


def test_explicit_prior_is_validated_against_its_original_contract_and_answer():
    value = expanded()
    _, data = prepare("question", value)
    turn_id, record = next(iter(value["service_input"]["prior_analyses"].items()))
    assert type(data["prior_analyses"][turn_id]) is c.ContractChecked
    assert c.to_data(data["prior_analyses"][turn_id]) == record["analysis"]
    assert (
        asdict(data["prior_question_contracts"][turn_id])["purpose"]
        == record["question_contract"]["purpose"]
    )
    assert (
        json.loads(json.dumps(_feedback_payload(data["recovery_feedback"])))
        == value["service_input"]["recovery_feedback"]
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "current",
        "foreign",
        "bad_quote",
        "bad_point",
        "bad_ref",
        "future_ref",
        "missing_contract",
        "extra",
        "empty_answer",
    ],
)
def test_invalid_prior_cannot_be_wrapped_as_checked(mutation):
    value = expanded()
    data = value["service_input"]
    prior = data["prior_analyses"]
    turn_id, entry = next(iter(prior.items()))
    if mutation == "current":
        prior[data["context"]["current_turn_id"]] = prior.pop(turn_id)
    elif mutation == "foreign":
        prior["not-in-this-history"] = prior.pop(turn_id)
    elif mutation == "bad_quote":
        entry["analysis"]["covered_points"][0]["answer_quotes"] = ["답변에 없는 다른 문장"]
    elif mutation == "bad_point":
        entry["analysis"]["covered_points"][0]["key"] = "not-asked"
    elif mutation == "bad_ref":
        entry["analysis"]["technical_assessment"]["evidence_refs"] = ["not-provided"]
    elif mutation == "future_ref":
        entry["question_contract"]["basis_refs"] = [
            {"kind": "answer_turn", "id": data["context"]["current_turn_id"]}
        ]
    elif mutation == "missing_contract":
        entry.pop("question_contract")
    elif mutation == "extra":
        entry["trusted"] = True
    else:
        data["context"]["history"][0]["answer"] = ""
    with pytest.raises(ExecutionError):
        prepare("question", value)


@pytest.mark.parametrize("mutation", ["version", "extra", "type", "size"])
def test_invalid_feedback_is_rejected_before_model_io(mutation):
    value = expanded()
    feedback = value["service_input"]["recovery_feedback"]
    if mutation == "version":
        feedback["version"] = "unknown-version"
    elif mutation == "extra":
        feedback["self_approved"] = True
    elif mutation == "type":
        feedback["recovery"] = "finish"
    else:
        feedback["review_reason_summary"] = "가" * 17000
    with pytest.raises(ExecutionError):
        prepare("question", value)


def test_absent_or_empty_prior_preserves_the_legacy_model_payload():
    old = base()
    empty = copy.deepcopy(old)
    empty["service_input"]["prior_analyses"] = {}
    prompt = c.PromptSpec("director", "director_v10", "configured-model", "policy")
    limits = c.CallLimits(30, 4096, 65536, 262144)

    def projected(value):
        _, data = prepare("question", value)
        return _input_payload(
            data["context"],
            prompt,
            limits,
            data["answer_analysis"],
            data["reference_texts"],
            data.get("prior_analyses"),
            data["tool_results"],
        )[0]

    assert projected(old) == projected(empty)
    assert old == base()


async def test_service_executor_passes_checked_prior_and_plan_only_feedback():
    value = expanded()
    requests = []
    root = value["service_input"]

    def factory():
        async def call(request, validator):
            requests.append(request)
            question = copy.deepcopy(root["question"])
            question["text"] = "동시에 같은 요청이 재시도된다면 중복을 어떻게 막겠어요?"
            question["question_contract"]["evaluation_keys"] = next(
                target["keys"]
                for target in root["context"]["evaluation_targets"]
                if target["persona"] == question["persona"]
            )
            raw = (
                {
                    "question": question,
                    "intent": "새 동시 조건의 검증",
                    "reason_summary": "과거 목적을 반복하지 않는다.",
                }
                if request.payload["operation"] == "plan"
                else {
                    "plan_valid": True,
                    "context_valid": True,
                    "wording_valid": True,
                    "contract_matches": True,
                    "safe_alternative": True,
                    "reason_summary": "검증용 응답",
                }
            )
            try:
                checked = validator(raw)
            except c.ContractError as error:
                raise AssertionError(
                    f"invalid mock {request.payload['operation']}: {error}"
                ) from error
            attempt = c.AttemptMetadata(
                len(requests),
                "fixture",
                "configured-model",
                request.prompt.version,
                request.schema_version,
                1,
                2,
                3,
                raw_output=json.dumps(raw, ensure_ascii=False),
            )
            return c.ModelResult(checked, None, (attempt,))

        return call

    executor = ServiceExecutor(
        {"director": c.PromptSpec("director", "director_v8", "configured-model", "policy")},
        c.CallLimits(30, 4096, 65536, 262144),
        factory,
    )
    await executor("question", value)
    prior_id = next(iter(root["prior_analyses"]))
    assert (
        requests[0].payload["prior_analyses"][prior_id]
        == root["prior_analyses"][prior_id]["analysis"]
    )
    assert (
        json.loads(json.dumps(requests[0].payload["recovery_feedback"]))
        == root["recovery_feedback"]
    )
    assert "recovery_feedback" not in requests[1].payload
    assert requests[0].payload["prior_analyses"] == requests[1].payload["prior_analyses"]
