"""실제 공통 gateway를 HTTP mock으로 실행해 Judge 예산·누출 경계를 검증한다."""

import importlib
import json

import httpx
from pydantic import SecretStr

from app.core.config import LLMSettings
from scripts.run_ai_evaluation import ModelAttemptBudget
from tests.agents.director_helpers import response


def llm():
    return LLMSettings(
        openai_api_key=SecretStr("private-judge-fixture-key"),
        llm_base_url="https://judge.example/v1",
        llm_default_model="configured-model",
        llm_timeout_seconds=2,
        llm_max_output_tokens=1024,
        llm_max_input_bytes=65536,
        llm_max_response_bytes=65536,
    )


def judge(budget, **kwargs):
    name = "scripts.ai_model_judge"
    assert importlib.util.find_spec(name) is not None, "명시적 모델 Judge 경계가 필요하다"
    from devon_ai import contracts as c

    module = importlib.import_module(name)
    return module.ModelJudge(
        c.PromptSpec(
            "evaluation_judge", "evaluation-judge-v1", "configured-model", "fixture judge"
        ),
        llm().call_limits(),
        budget.factory,
        **kwargs,
    )


RUBRIC = {
    "allowed": [{"id": "a1", "purpose": "원문 범위 안 질문"}],
    "forbidden": [{"id": "f1", "reason": "성과 추정"}],
    "review": "must-not-leak",
    "grader_controls": "must-not-leak",
}
VALID = {
    "verdict": "accept",
    "reason_summary": "허용 기준에 맞는 출력",
    "criterion_results": [
        {"id": "allowed:a1", "status": "satisfied", "reason": "관찰 범위 안이다"}
    ],
}


async def test_judge_sees_only_rubric_and_candidate_and_uses_separate_bounded_budget():
    requests = []

    def handle(request):
        requests.append(request)
        return response(VALID)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        budget = ModelAttemptBudget(1, llm(), http_client=http)
        evaluator = judge(budget)
        first = await evaluator(RUBRIC, "service-output")
        second = await evaluator(RUBRIC, "another-output")
        service_budget = ModelAttemptBudget(1, llm(), http_client=http)
    payload = json.loads(json.loads(requests[0].content)["input"][0]["content"][0]["text"])
    assert set(payload) == {"rubric", "candidate_output"}
    assert set(payload["rubric"]) == {"allowed", "forbidden"}
    assert "must-not-leak" not in json.dumps(payload)
    assert first.verdict == "accept" and len(first.attempts) == 1
    assert second.verdict is None and second.failure["stage"] == "budget"
    assert len(requests) == 1 and budget.remaining == 0 and service_budget.remaining == 1
    audit = json.dumps(evaluator.records)
    assert "private-judge-fixture-key" not in audit and "https://judge.example/v1" not in audit
    assert len(first.metadata["request_input_sha256"]) == 64
    assert len(first.metadata["judge_output_sha256"]) == 64


async def test_context_protocol_sends_actual_source_separately_and_no_review_labels():
    from judge_context import build_judge_context

    sent = []

    def handle(request):
        sent.append(json.loads(json.loads(request.content)["input"][0]["content"][0]["text"]))
        return response(VALID)

    context = build_judge_context(
        {
            "evidence": [
                {
                    "ref": "ev1",
                    "path": "src/task.ts",
                    "lines": "26-30",
                    "text": "const value = 1;",
                    "review": {"text": "hidden-review"},
                }
            ],
            "grader_controls": [{"text": "hidden-control"}],
        }
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        budget = ModelAttemptBudget(2, llm(), http_client=http)
        evaluator = judge(budget)
        result = await evaluator.judge_with_context(RUBRIC, "candidate", context)
    assert result.verdict == "accept" and len(sent) == 1 and budget.remaining == 1
    assert set(sent[0]) == {"rubric", "candidate_output", "source_context"}
    assert sent[0]["source_context"]["source"]["evidence"][0]["lines"] == "26-30"
    assert sent[0]["source_context"]["source"]["evidence"][0]["text"] == "const value = 1;"
    assert "hidden-review" not in json.dumps(sent) and "hidden-control" not in json.dumps(sent)
    assert "must-not-leak" not in json.dumps(sent)
    assert result.metadata["source_context_version"] == "judge-context.v1"
    assert len(result.metadata["source_context_sha256"]) == 64


async def test_direct_malformed_or_secret_context_never_reaches_model():
    from judge_context import build_judge_context

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: (_ for _ in ()).throw(AssertionError("no HTTP"))
        )
    ) as http:
        budget = ModelAttemptBudget(2, llm(), http_client=http)
        evaluator = judge(budget, sensitive_values=(llm().openai_api_key.get_secret_value(),))
        malformed = await evaluator.judge_with_context(
            RUBRIC, "candidate", {"schema_version": "unknown"}
        )
        secret = await evaluator.judge_with_context(
            RUBRIC,
            "candidate",
            build_judge_context({"materials": [{"text": llm().openai_api_key.get_secret_value()}]}),
        )
    assert malformed.failure["error_code"] == "judge_source_context_invalid"
    assert secret.failure["error_code"] == "judge_input_contains_configuration_secret"
    assert malformed.attempts == secret.attempts == () and budget.remaining == 2


async def test_unknown_criterion_is_semantic_failure_without_retry():
    requests = []

    def handle(request):
        requests.append(request)
        return response(
            {
                **VALID,
                "criterion_results": [
                    {"id": "forbidden:missing", "status": "violated", "reason": "없는 기준"}
                ],
            }
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        evaluator = judge(ModelAttemptBudget(2, llm(), http_client=http))
        result = await evaluator(RUBRIC, "candidate")
    assert result.verdict is None and result.failure["stage"] == "semantic"
    assert len(requests) == 1 and len(result.attempts) == 1


async def test_configured_secret_in_candidate_is_rejected_before_model_call():
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: (_ for _ in ()).throw(AssertionError("비밀값을 모델에 보내면 안 된다"))
        )
    ) as http:
        evaluator = judge(
            ModelAttemptBudget(2, llm(), http_client=http),
            sensitive_values=(llm().openai_api_key.get_secret_value(), llm().llm_base_url),
        )
        result = await evaluator(RUBRIC, llm().openai_api_key.get_secret_value())
    assert result.failure["error_code"] == "judge_input_contains_configuration_secret"
    assert result.attempts == ()


async def test_accept_without_any_criterion_reference_is_not_a_quality_result():
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: response({**VALID, "criterion_results": []}))
    ) as http:
        result = await judge(ModelAttemptBudget(2, llm(), http_client=http))(RUBRIC, "candidate")
    assert result.verdict is None and result.failure["stage"] == "semantic"


async def test_provider_echoed_secret_is_removed_from_audit_output():
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: response(
                {**VALID, "reason_summary": llm().openai_api_key.get_secret_value()}
            )
        )
    ) as http:
        evaluator = judge(
            ModelAttemptBudget(2, llm(), http_client=http),
            sensitive_values=(llm().openai_api_key.get_secret_value(),),
        )
        result = await evaluator(RUBRIC, "candidate")
    assert result.failure["error_code"] == "judge_output_contains_configuration_secret"
    assert llm().openai_api_key.get_secret_value() not in json.dumps(evaluator.records)


async def test_retry_and_later_judgments_share_the_global_budget():
    sent = []

    def handle(request):
        sent.append(request)
        return (
            httpx.Response(503, headers={"Retry-After": "0"}) if len(sent) == 1 else response(VALID)
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        budget = ModelAttemptBudget(3, llm(), http_client=http)
        evaluator = judge(budget)
        first = await evaluator(RUBRIC, "first")
        second = await evaluator(RUBRIC, "second")
        last = await evaluator(RUBRIC, "not-called")
    assert len(first.attempts) == 2 and len(second.attempts) == 1
    assert len(sent) == 3 and budget.remaining == 0 and last.failure["stage"] == "budget"
