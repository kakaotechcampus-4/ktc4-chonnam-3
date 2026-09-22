import asyncio
import json

import pytest

from devon_ai import contracts as c
from devon_ai.llm_tasks import answer_analysis as task


@pytest.fixture
def question():
    contract = c.QuestionContract(
        purpose="캐시 선정 근거 확인",
        required_points=(
            c.RequiredPoint("reads", "조회 특성"),
            c.RequiredPoint("writes", "수정 특성"),
            c.RequiredPoint("choice", "선정 이유"),
        ),
        assumptions=(),
        basis_refs=(),
        evaluation_scope="조회·수정 특성과 선정 이유",
    )
    candidate = c.Question(
        "tech_lead", "조회·수정 특성과 캐시 선정 이유는 무엇인가요?", "cache", contract, (), ()
    )
    return c.validate_question(
        candidate,
        review=c.QuestionReview(candidate.text, contract),
        allowed_personas=("tech_lead",),
        evidence_refs=frozenset(),
        basis_refs=frozenset(),
        jd_requirement_ids=frozenset(),
    )


@pytest.fixture
def answer():
    return c.SubmittedAnswer("answer", 2, "조회가 많아서 DB 부하를 줄이려고 캐시했습니다")


@pytest.fixture
def analysis():
    return {
        "evaluation_status": "evaluated",
        "sufficiency": "partial",
        "covered_points": [
            {"key": "reads", "answer_quotes": ["조회가 많아서"]},
            {"key": "choice", "answer_quotes": ["DB 부하를 줄이려고"]},
        ],
        "missing_points": ["writes"],
        "technical_assessment": {
            "explanation": "캐시 목적은 타당하나 구현 조건은 미확인",
            "answer_quotes": ["DB 부하를 줄이려고"],
            "evidence_refs": [],
            "limitations": ["현재 코드 근거 없음"],
        },
        "contribution_scope": "unknown",
        "contribution_quotes": [],
        "claim_checks": [],
        "needs_verification": False,
        "verification_requests": [],
        "limitations": ["실제 담당 범위 미확인"],
    }


@pytest.fixture
def model_request():
    return c.ModelRequest(
        "answer_analysis_v1",
        "fixture-model",
        "BE injected common rubric",
        "fixture-p1",
        '{"type":"object"}',
        "fixture-s1",
        "{}",
        1.0,
        100,
    )


@pytest.fixture
def run_analysis(model_request, question, answer):
    def run(*outputs, **kwargs):
        requests = []
        outcomes = iter(outputs)

        async def client(value):
            requests.append(value)
            raw = next(outcomes)
            if isinstance(raw, BaseException):
                raise raw
            return c.ModelResponse(raw if isinstance(raw, str) else json.dumps(raw), "actual-model")

        args = dict(
            request=model_request, question=question, question_turn=2, answer=answer, client=client
        )
        args.update(kwargs)
        result = asyncio.run(task.analyze_answer(**args))
        return result, requests

    return run
