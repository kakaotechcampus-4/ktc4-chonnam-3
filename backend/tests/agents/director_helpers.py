"""Director 서비스·Context 검증이 공유하는 질문·분석·DB 준비 자료."""

import json
from dataclasses import asdict

import httpx
from devon_ai import contracts as c

from app.core.config import Settings
from app.db.models import InterviewSession, InterviewTurn, PromptVersion


def contract():
    return c.QuestionContract("역할 설명", (c.RequiredPoint("role", "본인 역할"),), (), (), "역할")


def analysis():
    return c.AnswerAnalysis(
        "evaluated",
        "sufficient",
        (c.CoveredPoint("role", ("팀원 담당입니다",)),),
        (),
        c.TechnicalAssessment("기술적 판단 보류", (), (), ("코드 미확인",)),
        c.ContributionScope("teammate", ("팀원 담당입니다",)),
        (),
        False,
        (),
        ("기술 미확인",),
    )


def settings():
    return Settings(
        _env_file=None,
        openai_api_key="fixture-key",
        llm_timeout_seconds=2,
        llm_max_output_tokens=2048,
        llm_max_input_bytes=262144,
        llm_max_response_bytes=262144,
    ).require_llm()


def response(data, model="fixture-model"):
    raw = json.dumps(data, ensure_ascii=False)
    return httpx.Response(
        200,
        json={
            "id": "fixture",
            "model": model,
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "status": "completed",
                    "content": [{"type": "output_text", "text": raw}],
                }
            ],
            "usage": {"input_tokens": 8, "output_tokens": 6},
        },
    )


async def seed_turns(sessions, seed, count=1):
    order = ["hr_manager"] + ["tech_lead"] * 6 + ["domain_lead"] * 2
    async with sessions.begin() as db:
        interview = await db.get(InterviewSession, seed["interview_id"])
        interview.current_turn = count
        db.add(
            PromptVersion(
                task_name="answer_analysis",
                version="analysis_v1",
                model="analysis-model",
                template="분석 fixture",
                is_active=True,
            )
        )
        for index, persona in enumerate(order[:count], 1):
            db.add(
                InterviewTurn(
                    interview_session_id=seed["interview_id"],
                    turn_no=index,
                    persona=persona,
                    question_text="본인의 역할을 설명해 주세요.",
                    question_contract=asdict(contract()),
                    topic_code="role",
                    status="asked" if index == count else "answered",
                    answer_text=None if index == count else "팀원 담당입니다",
                )
            )


def plan(persona="hr_manager"):
    return {
        "question": asdict(
            c.Question(persona, "본인의 역할을 설명해 주세요.", "role", contract(), (), ())
        ),
        "intent": "역할 확인",
        "reason_summary": "현재 자료에 맞는 질문",
    }


def approved_review():
    return {
        "plan_valid": True,
        "context_valid": True,
        "wording_valid": True,
        "contract_matches": True,
        "safe_alternative": True,
        "reason_summary": "적절한 질문",
    }
