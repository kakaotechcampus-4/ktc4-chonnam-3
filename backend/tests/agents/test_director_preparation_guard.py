"""준비 작업 소유권이 바뀐 늦은 Director 결과는 질문으로 저장하지 않는다."""

import json
from uuid import uuid4

import httpx
from sqlalchemy import func, select

from app.db.models import InterviewSession, InterviewTurn, LLMCallRecord
from tests.agents.director_helpers import (
    approved_review,
    plan,
    response,
    seed_turns,
    settings,
)


async def test_rejected_preparation_owner_cannot_start_a_provider_call(agent_sessions, agent_seed):
    from app.features.interview.director_service import start_director

    await seed_turns(agent_sessions, agent_seed, 0)
    calls = []

    async def provider(request):
        calls.append(request)
        raise AssertionError("소유권을 잃은 준비 작업은 모델을 호출하면 안 된다")

    call_id = uuid4()
    async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as http:
        result = await start_director(
            agent_sessions,
            user_id=agent_seed["owner"],
            interview_id=agent_seed["interview_id"],
            call_id=call_id,
            settings=settings(),
            http_client=http,
            preparation_guard=lambda interview: False,
        )
    assert result.discard_reason == "context_changed" and result.turn_id is None
    assert calls == []
    async with agent_sessions() as db:
        assert await db.get(LLMCallRecord, call_id) is None
        assert await db.scalar(select(func.count()).select_from(InterviewTurn)) == 0


async def test_changed_preparation_owner_cannot_save_a_completed_director_result(
    agent_sessions, agent_seed
):
    from app.features.interview.director_service import start_director

    await seed_turns(agent_sessions, agent_seed, 0)
    async with agent_sessions.begin() as db:
        interview = await db.get(InterviewSession, agent_seed["interview_id"])
        interview.context_state = {"prepare_job_id": "original-worker"}
    operations = []

    async def provider(request):
        body = json.loads(request.content)
        payload = json.loads(body["input"][0]["content"][0]["text"])
        operations.append(payload["operation"])
        if payload["operation"] == "review":
            # 외부 I/O 동안 새 소유자가 생겨도 질문 자료 Context는 우연히 같을 수 있다.
            async with agent_sessions.begin() as db:
                interview = await db.get(InterviewSession, agent_seed["interview_id"])
                interview.context_state = {"prepare_job_id": "replacement-worker"}
            return response(approved_review())
        return response(plan())

    def owns_preparation(interview):
        return (interview.context_state or {}).get("prepare_job_id") == "original-worker"

    call_id = uuid4()
    async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as http:
        result = await start_director(
            agent_sessions,
            user_id=agent_seed["owner"],
            interview_id=agent_seed["interview_id"],
            call_id=call_id,
            settings=settings(),
            http_client=http,
            preparation_guard=owns_preparation,
        )
    assert result.discard_reason == "context_changed" and result.turn_id is None
    assert operations == ["plan", "review"]
    async with agent_sessions() as db:
        interview = await db.get(InterviewSession, agent_seed["interview_id"])
        record = await db.get(LLMCallRecord, call_id)
        assert interview.current_turn == 0
        assert interview.context_state == {"prepare_job_id": "replacement-worker"}
        assert record.discard_reason == "context_changed" and len(record.attempts) == 2
        assert await db.scalar(select(func.count()).select_from(InterviewTurn)) == 0
