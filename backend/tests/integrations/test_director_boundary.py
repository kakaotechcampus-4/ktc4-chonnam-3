"""Real AI/BE calling boundary with a fake HTTP provider; no model or DB writes."""

import asyncio
import json
from dataclasses import asdict, replace
from functools import partial

import httpx
import pytest
from devon_ai import contracts as c
from devon_ai.agents.director import agent
from pydantic import SecretStr

from app.agents.contracts import to_turn_jsonb
from app.integrations.llm.client import CallBudget, call_model


@pytest.fixture
def context():
    return c.Context(
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
    )


@pytest.fixture
def contract():
    return c.QuestionContract(
        "본인의 역할 소개",
        (c.RequiredPoint("role", "본인 역할"),),
        (),
        (),
        "역할 소개",
    )


def candidate(contract):
    return c.Question("hr_manager", "맡은 역할을 소개해 주세요.", "role", contract, (), ())


def wire(value):
    return json.loads(json.dumps(asdict(value), ensure_ascii=False))


def response(text):
    return {
        "id": "resp_director_fixture",
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
    }


def provider(outputs, sent):
    replies = iter(outputs)

    def transport(request):
        sent.append(request)
        return httpx.Response(200, json=response(next(replies)))

    return httpx.MockTransport(transport)


async def generate(http, context, contract, review, *, budget=None, limits=None, **options):
    model_call = partial(
        call_model,
        api_key=SecretStr("fixture-key"),
        http_client=http,
        budget=budget if budget is not None else CallBudget(),
    )
    return await agent.generate_question(
        context,
        contract,
        prompt=c.PromptSpec("director", "director_v1", "configured-model", "fixture prompt"),
        limits=limits if limits is not None else c.CallLimits(1, 512, 65536, 65536),
        model_call=model_call,
        review=review,
        **options,
    )


async def test_http_request_and_checked_question_reach_existing_jsonb_boundary(context, contract):
    sent = []
    reviewed = []
    raw = json.dumps(wire(candidate(contract)), ensure_ascii=False)

    async def review(request, question):
        reviewed.append((request, question))
        return c.QuestionReview(question.text, contract)

    async with httpx.AsyncClient(transport=provider([raw], sent)) as http:
        result = await generate(http, context, contract, review)

    assert result.succeeded and result.data.data == candidate(contract)
    assert len(sent) == len(reviewed) == 1
    body = json.loads(sent[0].content)
    assert str(sent[0].url) == "https://api.openai.com/v1/responses"
    assert body["model"] == "configured-model"
    assert body["instructions"] == "fixture prompt"
    assert body["store"] is False and body["max_output_tokens"] == 512
    payload = json.loads(body["input"][0]["content"][0]["text"])
    assert set(payload) == {"context", "question_contract", "reference_texts", "answer_analysis"}
    assert payload["question_contract"] == wire(contract)
    assert payload["context"] == wire(context)
    assert payload["reference_texts"] == [] and payload["answer_analysis"] is None
    request, question = reviewed[0]
    assert json.loads(json.dumps(request.payload)) == payload
    assert question == candidate(contract)
    assert request.max_attempts == 2
    schema = body["text"]["format"]["schema"]
    assert body["text"]["format"]["strict"] is True
    assert set(schema["properties"]) == {
        "persona",
        "text",
        "topic_code",
        "question_contract",
        "evidence_refs",
        "jd_requirement_ids",
    }
    assert set(schema["required"]) == set(schema["properties"])
    assert schema["additionalProperties"] is False
    assert to_turn_jsonb(result, column="question_contract") == wire(contract)
    assert result.attempts[0].model == "actual-model-snapshot"
    assert result.attempts[0].raw_output == raw
    assert result.attempts[0].input_tokens == 100
    assert "fixture-key" not in repr(result) and raw not in repr(result)


@pytest.mark.parametrize("stage", ["parse", "schema"])
async def test_common_boundary_retries_invalid_generation_once_then_reviews(
    context, contract, stage
):
    sent = []
    reviewed = []
    raw = wire(candidate(contract))
    invalid = "not-json" if stage == "parse" else json.dumps({**raw, "text": 123})

    async def review(request, question):
        reviewed.append(question)
        return c.QuestionReview(question.text, contract)

    async with httpx.AsyncClient(transport=provider([invalid, json.dumps(raw)], sent)) as http:
        result = await generate(http, context, contract, review)

    assert result.succeeded and len(sent) == 2
    assert reviewed == [candidate(contract)]
    assert [item.attempt for item in result.attempts] == [1, 2]
    assert [item.error_stage for item in result.attempts] == [stage, None]


@pytest.mark.parametrize("change", ["persona", "plan"])
async def test_semantic_generation_failure_stops_before_review(context, contract, change):
    sent = []
    raw = wire(candidate(contract))
    if change == "persona":
        raw["persona"] = "tech_lead"
    else:
        raw["question_contract"]["purpose"] = "다른 목적"

    async def forbidden(*args):
        pytest.fail("a rejected model candidate must not reach independent review")

    async with httpx.AsyncClient(transport=provider([json.dumps(raw)], sent)) as http:
        result = await generate(http, context, contract, forbidden)

    assert result.failure.stage == "semantic" and result.data is None
    assert len(sent) == len(result.attempts) == 1
    assert result.attempts[0].error_stage == "semantic"


async def test_one_remaining_call_does_not_retry_parse_failure(context, contract):
    context = replace(context, limits=c.ContextLimits(1, 0, "fixture"))
    sent = []

    async def forbidden(*args):
        pytest.fail("failed generation must not reach review")

    async with httpx.AsyncClient(transport=provider(["not-json"], sent)) as http:
        result = await generate(http, context, contract, forbidden)

    assert result.failure.stage == "parse" and result.data is None
    assert len(sent) == len(result.attempts) == 1


@pytest.mark.parametrize("mode", ["semantic", "schema", "mismatch", "timeout"])
async def test_independent_review_failure_never_retries_generation(context, contract, mode, caplog):
    sent = []
    reviewed = []

    async def review(request, question):
        reviewed.append(question)
        if mode in ("semantic", "schema"):
            raise c.ContractError(mode, "private-review-detail")
        if mode == "timeout":
            raise TimeoutError("private-review-detail")
        return c.QuestionReview("다른 문장", contract)

    async with httpx.AsyncClient(
        transport=provider([json.dumps(wire(candidate(contract)))], sent)
    ) as http:
        result = await generate(http, context, contract, review)

    assert result.data is None and not result.succeeded
    assert len(sent) == len(reviewed) == len(result.attempts) == 1
    expected = "director_review_timeout" if mode == "timeout" else "director_review_failed"
    assert result.failure.error_code == expected
    if mode != "timeout":
        assert result.failure.stage == "semantic"
    # A successful generation attempt is preserved; reviewer errors are not provider retries.
    assert result.attempts[0].error_stage is None
    assert "private-review-detail" not in repr(result) + caplog.text


async def test_unexpected_reviewer_error_propagates_without_another_request(context, contract):
    sent = []

    async def review(request, question):
        raise RuntimeError("reviewer bug")

    async with httpx.AsyncClient(
        transport=provider([json.dumps(wire(candidate(contract)))], sent)
    ) as http:
        with pytest.raises(RuntimeError, match="reviewer bug"):
            await generate(http, context, contract, review)
    assert len(sent) == 1


async def test_review_deadline_cancels_a_stalled_reviewer_without_regeneration(context, contract):
    sent = []
    finished = asyncio.Event()

    async def review(request, question):
        try:
            await asyncio.Event().wait()
        finally:
            finished.set()

    async with httpx.AsyncClient(
        transport=provider([json.dumps(wire(candidate(contract)))], sent)
    ) as http:
        result = await asyncio.wait_for(
            generate(http, context, contract, review, limits=c.CallLimits(0.05, 512, 65536, 65536)),
            timeout=2,
        )

    assert result.failure.stage == "timeout" and result.data is None
    assert result.failure.error_code == "director_review_timeout"
    assert finished.is_set() and len(sent) == len(result.attempts) == 1


async def test_one_request_attempt_can_use_the_second_shared_budget_slot(context, contract):
    sent = []
    budget = CallBudget()
    raw = json.dumps(wire(candidate(contract)))
    reviewed = []

    async def review(request, question):
        reviewed.append(request.max_attempts)
        return c.QuestionReview(question.text, contract)

    context = replace(context, limits=c.ContextLimits(1, 0, "fixture"))
    async with httpx.AsyncClient(transport=provider([raw, raw], sent)) as http:
        first = await generate(http, context, contract, review, budget=budget)
        second = await generate(http, context, contract, review, budget=budget)
        third = await generate(http, context, contract, review, budget=budget)

    assert first.succeeded and second.succeeded
    assert [item.attempt for item in second.attempts] == [1, 2]
    assert third.failure.stage == "budget" and third.data is None
    assert len(sent) == 2 and reviewed == [1, 1]


async def test_posting_source_reaches_generation_and_independent_review_unchanged(
    context, contract
):
    ref = c.BasisRef("job_posting", "posting-1")
    contract = replace(contract, basis_refs=(ref,))
    source = "공고 원문: 협업 경험을 존중합니다."
    sent = []
    reviewed = []

    async def review(request, question):
        reviewed.append(request.payload["reference_texts"])
        return c.QuestionReview(question.text, contract)

    async with httpx.AsyncClient(
        transport=provider([json.dumps(wire(candidate(contract)))], sent)
    ) as http:
        result = await generate(http, context, contract, review, reference_texts={ref: source})

    assert result.succeeded
    payload = json.loads(json.loads(sent[0].content)["input"][0]["content"][0]["text"])
    assert reviewed == [[{"kind": "job_posting", "id": "posting-1", "text": source}]]
    assert reviewed[0] == payload["reference_texts"]
