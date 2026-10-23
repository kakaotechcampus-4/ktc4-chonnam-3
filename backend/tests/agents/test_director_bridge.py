"""공급자 HTTP만 대체하고 질문 복원과 AI 어댑터의 실제 호출 예산을 확인한다."""

import json
from dataclasses import asdict, replace

import httpx
import pytest
from devon_ai import contracts as c

from app.agents.director.agent import execute_director
from app.core.config import Settings
from app.db.models import InterviewTurn
from app.features.interview.agent_context import AgentStateError
from app.features.interview.answer_context import restored_question
from app.integrations.llm.client import CallBudget
from app.llm_tasks.answer_analysis import analyze_answer


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


def question():
    return c.Question(
        "hr_manager",
        "프로젝트에서 맡은 역할을 소개해 주세요.",
        "role",
        c.QuestionContract(
            "본인 역할 소개", (c.RequiredPoint("role", "본인이 맡은 역할"),), (), (), "역할"
        ),
        (),
        (),
    )


def settings():
    return Settings(
        _env_file=None,
        openai_api_key="fixture-key",
        proxy_token="fixture-proxy-key",
        chat_proxy_url="https://model.example.test/v1",
        llm_timeout_seconds=2,
        llm_max_output_tokens=2048,
        llm_max_input_bytes=262144,
        llm_max_response_bytes=262144,
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
            "usage": {"input_tokens": 8, "output_tokens": 6},
        },
    )


async def test_director_adapter_shares_two_attempts_and_forwards_provider_settings():
    candidate = question()
    outputs = [
        dict(question=asdict(candidate), intent="역할 확인", reason_summary="자기소개"),
        dict(
            plan_valid=True,
            context_valid=True,
            wording_valid=True,
            contract_matches=True,
            safe_alternative=True,
            reason_summary="목적에 맞는 질문",
        ),
    ]
    payloads = []

    async def provider(request):
        assert str(request.url) == "https://model.example.test/v1/responses"
        body = json.loads(request.content)
        assert body["model"] == "fixture-model"
        payloads.append(json.loads(body["input"][0]["content"][0]["text"]))
        return response(outputs.pop(0))

    attempts = []
    budget = CallBudget()
    async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as http:
        result = await execute_director(
            context(),
            prompt=c.PromptSpec("director", "fixture", "fixture-model", "fixture"),
            settings=settings(),
            budget=budget,
            http_client=http,
            attempt_sink=attempts,
        )
    assert result.succeeded and result.data.question.data == candidate
    assert [payload["operation"] for payload in payloads] == ["plan", "review"]
    assert result.attempts == tuple(attempts)
    assert [attempt.attempt for attempt in attempts] == [1, 2]


async def test_answer_adapter_cannot_retry_past_the_requested_single_attempt():
    candidate = question()
    checked = c.validate_question(
        candidate,
        review=c.QuestionReview(candidate.text, candidate.question_contract),
        allowed_personas=(candidate.persona,),
        evidence_refs=frozenset(),
        basis_refs=frozenset(),
        jd_requirement_ids=frozenset(),
    )
    ctx = replace(
        context(),
        current_turn_id="turn-1",
        current_question_contract=candidate.question_contract,
    )
    requests = []

    async def provider(request):
        requests.append(request)
        assert str(request.url) == "https://model.example.test/v1/responses"
        return response({"invalid": True})

    attempts = []
    async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as http:
        result = await analyze_answer(
            ctx,
            checked,
            turn_id="turn-1",
            answer_text="제가 구현했습니다.",
            prompt=c.PromptSpec("answer_analysis", "fixture", "fixture-model", "fixture"),
            settings=settings(),
            budget=CallBudget(),
            max_attempts=1,
            http_client=http,
            attempt_sink=attempts,
        )
    assert not result.succeeded and result.failure.stage == "schema"
    assert len(requests) == len(attempts) == 1
    assert result.attempts == tuple(attempts)


def test_restored_question_uses_the_original_stored_contract():
    candidate = question()
    turn = InterviewTurn(
        turn_no=1,
        persona=candidate.persona,
        question_text=candidate.text,
        topic_code=candidate.topic_code,
        question_contract=json.loads(json.dumps(asdict(candidate.question_contract))),
        jd_requirement_ids=[],
    )
    restored = restored_question(turn, context())
    assert restored.data == candidate
    turn.question_contract = {"invalid": True}
    with pytest.raises(AgentStateError, match="question_contract_invalid"):
        restored_question(turn, context())
