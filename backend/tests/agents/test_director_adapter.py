"""실제 AI Director와 공통 Gateway를 HTTP mock으로 연결해 BE 경계를 검증한다."""

import asyncio
import json
from dataclasses import replace

import httpx
import pytest
from devon_ai import contracts as c

from app.agents.director import agent
from app.core.config import LLMSettings
from app.integrations.llm.client import CallBudget


@pytest.fixture
def inputs():
    contract = c.QuestionContract(
        "역할 소개", (c.RequiredPoint("role", "본인 역할"),), (), (), "역할 소개"
    )

    async def review(request, question):
        return c.QuestionReview(question.text, question.question_contract)

    return {
        "context": c.Context(
            "interview-1",
            None,
            1,
            9,
            (),
            ("hr_manager",),
            (),
            (),
            (),
            None,
            (),
            (),
            c.ContextLimits(2, 0, "fixture"),
        ),
        "question_contract": contract,
        "prompt": c.PromptSpec("director", "director_v1", "prompt-model", "질문 생성"),
        "review": review,
        "settings": LLMSettings(
            openai_api_key="fixture-key",
            llm_default_model="different-default-model",
            llm_timeout_seconds=1,
            llm_max_output_tokens=512,
            llm_max_input_bytes=65536,
            llm_max_response_bytes=65536,
        ),
        "budget": CallBudget(),
    }


def question_text(**changes):
    return json.dumps(
        {
            "persona": "hr_manager",
            "text": "맡은 역할을 소개해 주세요.",
            "topic_code": "role",
            "evidence_refs": [],
            "jd_requirement_ids": [],
            **changes,
        },
        ensure_ascii=False,
    )


def response(text):
    return httpx.Response(
        200,
        json={
            "id": "response-fixture",
            "model": "actual-model-snapshot",
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "status": "completed",
                    "content": [{"type": "output_text", "text": text}],
                }
            ],
            "usage": {"input_tokens": 100, "output_tokens": 60},
        },
    )


def provider(outputs, sent):
    replies = iter(outputs)

    def handle(request):
        sent.append(request)
        return response(next(replies))

    return httpx.MockTransport(handle)


async def test_prompt_model_limits_and_attempt_metadata_survive_adapter(inputs):
    sent, reviewed = [], []
    raw = question_text()

    async def review(request, question):
        reviewed.append(request)
        return c.QuestionReview(question.text, question.question_contract)

    async with httpx.AsyncClient(transport=provider([raw], sent)) as http:
        result = await agent.generate_question(**{**inputs, "review": review}, http_client=http)
        assert not http.is_closed

    assert result.succeeded and isinstance(result.data, c.ContractChecked)
    assert result.data.data.question_contract == inputs["question_contract"]
    assert result.data.data.text == "맡은 역할을 소개해 주세요."
    body = json.loads(sent[0].content)
    assert body["model"] == "prompt-model" and body["max_output_tokens"] == 512
    assert body["instructions"] == "질문 생성" and body["store"] is False
    assert sent[0].headers["authorization"] == "Bearer fixture-key"
    assert reviewed[0].limits == c.CallLimits(1, 512, 65536, 65536)
    assert "fixture-key" not in repr(reviewed[0]) + repr(result)
    (metadata,) = result.attempts
    assert metadata.model == "actual-model-snapshot" and metadata.raw_output == raw
    assert metadata.prompt_version == "director_v1" and metadata.schema_version == "2"
    assert metadata.input_tokens == 100 and metadata.output_tokens == 60
    assert metadata.response_id == "response-fixture" and metadata.latency_ms >= 0


@pytest.mark.parametrize("recover", [False, True])
async def test_parse_retry_is_owned_by_gateway_and_stops_at_two_attempts(inputs, recover):
    sent, attempts = [], []
    outputs = ["not-json", question_text() if recover else "still-not-json"]
    async with httpx.AsyncClient(transport=provider(outputs, sent)) as http:
        result = await agent.generate_question(**inputs, http_client=http, attempt_sink=attempts)
    assert len(sent) == 2 and [item.attempt for item in result.attempts] == [1, 2]
    assert attempts == list(result.attempts)
    assert result.succeeded is recover
    assert result.attempts[0].error_stage == "parse"
    if not recover:
        assert result.data is None and result.failure.stage == "parse"


async def test_provider_timeout_keeps_two_failed_attempts(inputs):
    sent = []

    def timeout(request):
        sent.append(request)
        raise httpx.ReadTimeout("fixture timeout", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(timeout)) as http:
        result = await agent.generate_question(**inputs, http_client=http)
    assert result.data is None and result.failure.stage == "timeout"
    assert len(sent) == 2 and [item.error_stage for item in result.attempts] == ["timeout"] * 2


async def test_semantic_failure_does_not_reach_review_or_retry(inputs):
    sent = []

    async def forbidden(request, question):
        pytest.fail("의미 검증에 실패한 질문이 검토기에 전달됨")

    async with httpx.AsyncClient(
        transport=provider([question_text(persona="tech_lead")], sent)
    ) as http:
        result = await agent.generate_question(**{**inputs, "review": forbidden}, http_client=http)
    assert result.data is None and result.failure.stage == "semantic"
    assert len(sent) == len(result.attempts) == 1


@pytest.mark.parametrize("stage", ["semantic", "schema"])
async def test_reviewer_rejection_retains_generation_metadata_without_retry(inputs, stage):
    sent = []

    async def reject(request, question):
        raise c.ContractError(stage, "검토 거절")

    async with httpx.AsyncClient(transport=provider([question_text()], sent)) as http:
        result = await agent.generate_question(**{**inputs, "review": reject}, http_client=http)
    assert result.data is None and result.failure.error_code == "director_review_failed"
    assert len(sent) == len(result.attempts) == 1
    assert result.attempts[0].error_stage is None


async def test_configured_review_timeout_cancels_review_without_another_generation(inputs):
    sent, finished = [], asyncio.Event()

    async def review(request, question):
        try:
            await asyncio.Event().wait()
        finally:
            finished.set()

    inputs["settings"] = inputs["settings"].model_copy(update={"llm_timeout_seconds": 0.02})
    async with httpx.AsyncClient(transport=provider([question_text()], sent)) as http:
        result = await asyncio.wait_for(
            agent.generate_question(
                **{**inputs, "review": review},
                http_client=http,
            ),
            timeout=2,
        )
    assert result.failure.error_code == "director_review_timeout" and finished.is_set()
    assert len(sent) == len(result.attempts) == 1


async def test_same_budget_is_shared_across_director_calls(inputs):
    sent, attempts = [], []
    inputs["attempt_sink"] = attempts
    async with httpx.AsyncClient(transport=provider([question_text()] * 2, sent)) as http:
        first = await agent.generate_question(**inputs, http_client=http)
        second = await agent.generate_question(**inputs, http_client=http)
        exhausted = await agent.generate_question(**inputs, http_client=http)
    assert first.succeeded and second.succeeded
    assert [item.attempt for item in first.attempts] == [1]
    assert [item.attempt for item in second.attempts] == [2]
    assert exhausted.failure.stage == "budget" and exhausted.attempts == ()
    assert len(sent) == 2
    assert attempts == [*first.attempts, *second.attempts]
