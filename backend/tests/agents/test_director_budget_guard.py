"""실제 gateway 예산과 Context가 달라도 미검토 질문 생성에 시도를 쓰지 않는다."""

import json
from dataclasses import asdict

import httpx
import pytest
from devon_ai import contracts as c

from app.agents.director.agent import execute_director
from app.core.config import Settings
from app.integrations.llm.client import CallBudget, call_model

PROMPT = c.PromptSpec("director", "fixture", "fixture-model", "fixture")


def context(remaining=2):
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
        c.ContextLimits(remaining, 0, "fixture"),
    )


def settings():
    return Settings(
        _env_file=None,
        openai_api_key="fixture-key",
        llm_timeout_seconds=1,
        llm_max_output_tokens=512,
        llm_max_input_bytes=65536,
        llm_max_response_bytes=65536,
    ).require_llm()


def response(value):
    return httpx.Response(
        200,
        json={
            "id": "fixture",
            "model": "fixture-model",
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "status": "completed",
                    "content": [{"type": "output_text", "text": json.dumps(value)}],
                }
            ],
            "usage": {"input_tokens": 1, "output_tokens": 1},
        },
    )


@pytest.mark.parametrize("used", [1, 2])
async def test_spent_budget_stops_before_a_plan_can_consume_the_review_slot(used):
    sent = []
    candidate = c.Question(
        "hr_manager",
        "역할을 소개해 주세요.",
        "role",
        c.QuestionContract("역할", (c.RequiredPoint("role", "역할"),), (), (), "역할"),
        (),
        (),
    )

    async def provider(request):
        sent.append(request)
        return response({"question": asdict(candidate), "intent": "역할", "reason_summary": "역할"})

    config, budget = settings(), CallBudget()
    request = c.ModelRequest(PROMPT, {}, "Fixture", "1", {}, config.call_limits(), max_attempts=1)
    async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as http:
        for _ in range(used):
            previous = await call_model(
                request,
                lambda raw: raw,
                api_key=config.openai_api_key,
                base_url=config.llm_base_url,
                http_client=http,
                budget=budget,
            )
            assert previous.succeeded
        result = await execute_director(
            context(),
            prompt=PROMPT,
            settings=config,
            budget=budget,
            http_client=http,
        )
    assert result.data is None and result.failure.stage == "budget"
    assert result.attempts == ()
    assert len(sent) == used


async def test_context_allowance_is_clamped_to_the_real_fresh_budget():
    payloads = []
    candidate = c.Question(
        "hr_manager",
        "역할을 소개해 주세요.",
        "role",
        c.QuestionContract("역할", (c.RequiredPoint("role", "역할"),), (), (), "역할"),
        (),
        (),
    )

    async def provider(request):
        body = json.loads(request.content)
        payload = json.loads(body["input"][0]["content"][0]["text"])
        payloads.append(payload)
        if payload["operation"] == "plan":
            return response(
                {"question": asdict(candidate), "intent": "역할", "reason_summary": "역할"}
            )
        return response(
            dict(
                plan_valid=True,
                context_valid=True,
                wording_valid=True,
                contract_matches=True,
                safe_alternative=True,
                reason_summary="유효",
            )
        )

    supplied = context(remaining=3)
    async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as http:
        result = await execute_director(
            supplied,
            prompt=PROMPT,
            settings=settings(),
            budget=CallBudget(),
            http_client=http,
        )
    assert result.succeeded
    assert [payload["context"]["limits"]["remaining_calls"] for payload in payloads] == [2, 2]
    assert supplied.limits.remaining_calls == 3


async def test_terminal_failure_is_preserved_without_reentering_the_provider():
    sent = []

    async def provider(request):
        sent.append(request)
        return response({})

    def reject(raw):
        raise c.ContractError("semantic", "fixture")

    config, budget = settings(), CallBudget()
    request = c.ModelRequest(PROMPT, {}, "Fixture", "1", {}, config.call_limits(), max_attempts=1)
    async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as http:
        original = await call_model(
            request,
            reject,
            api_key=config.openai_api_key,
            base_url=config.llm_base_url,
            http_client=http,
            budget=budget,
        )
        result = await execute_director(
            context(),
            prompt=PROMPT,
            settings=config,
            budget=budget,
            http_client=http,
        )
    assert result.failure is original.failure
    assert result.data is None and result.attempts == ()
    assert len(sent) == 1
