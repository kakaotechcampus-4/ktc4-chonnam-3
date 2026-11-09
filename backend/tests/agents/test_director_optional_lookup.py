"""선택 검색 실패가 확정한 답변 분석과 다음 질문을 없애지 않는다."""

import json
from dataclasses import asdict, replace
from uuid import uuid4

import httpx
import pytest
from devon_ai import contracts as c
from sqlalchemy import select

from app.core.config import Settings
from app.db.models import InterviewSession, InterviewTurn, LLMCallRecord, PromptVersion
from app.features.interview import external_knowledge
from app.features.interview.director_service import process_answer
from tests.agents.director_helpers import (
    analysis,
    approved_review,
    plan,
    response,
    seed_turns,
    settings,
)


@pytest.mark.parametrize("case", ["unsafe_query", "unexpected_failure"])
async def test_optional_lookup_failure_keeps_t3_and_generates_the_next_question(
    agent_sessions, agent_seed, monkeypatch, case
):
    await seed_turns(agent_sessions, agent_seed)
    async with agent_sessions.begin() as db:
        active = await db.scalar(
            select(PromptVersion).where(PromptVersion.task_name == "answer_analysis")
        )
        active.version = "answer_analysis_v2"
    if case == "unexpected_failure":

        async def fail(*args, **kwargs):
            raise RuntimeError("provider-private-detail")

        monkeypatch.setattr(external_knowledge, "retrieve_external_knowledge", fail)
    requests = []

    async def provider(request):
        payload = json.loads(json.loads(request.content)["input"][0]["content"][0]["text"])
        requests.append(payload)
        if "operation" not in payload:
            query = "me@example.invalid Redis" if case == "unsafe_query" else "Redis sessions"
            return response(
                asdict(
                    replace(
                        analysis(),
                        needs_verification=True,
                        external_queries=(c.ExternalQueryRequest(query, "일반 개념 보완"),),
                    )
                )
            )
        return response(
            approved_review() if payload["operation"] == "review" else plan("tech_lead")
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as http:
        result = await process_answer(
            agent_sessions,
            user_id=agent_seed["owner"],
            interview_id=agent_seed["interview_id"],
            turn_no=1,
            text="팀원 담당입니다",
            call_id=uuid4(),
            settings=settings(),
            external_settings=Settings(_env_file=None, tavily_api_key="fixture"),
            http_client=http,
        )
    assert result.failure is None and result.next_turn_id is not None and result.accepted
    assert len(requests) == 3
    trace = requests[1]["context"]["external_searches"][0]
    assert trace["status"] == "tool_error" and trace["source_ids"] == []
    expected = "unsafe_external_query" if case == "unsafe_query" else "external_lookup_unavailable"
    assert trace["error_code"] == expected
    assert "provider-private-detail" not in json.dumps(trace)
    async with agent_sessions() as db:
        original = await db.scalar(select(InterviewTurn).where(InterviewTurn.turn_no == 1))
        assert original.analysis["needs_verification"] is True
        records = list(await db.scalars(select(LLMCallRecord)))
        t3 = [item for item in records if item.task_name == "answer_analysis"]
        assert len(t3) == 1 and t3[0].failure is None and t3[0].turn_id == original.id
        interview = await db.get(InterviewSession, agent_seed["interview_id"])
        assert "2" in interview.context_state["director_retry_inputs"]
