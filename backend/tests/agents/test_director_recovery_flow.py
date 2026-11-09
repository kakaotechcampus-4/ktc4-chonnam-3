"""후보 복구 오류코드가 준비·턴 흐름에서 실행·대체 없이 기록만 남기는지 PostgreSQL로 확인한다."""

import json
from dataclasses import asdict
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import func, select
from structlog.testing import capture_logs

from app.db.models import InterviewSession, InterviewTurn, LLMCallRecord
from app.features.interview.director_service import recovery_code
from tests.agents.director_helpers import (
    analysis,
    approved_review,
    plan,
    response,
    seed_turns,
    settings,
)
from tests.agents.test_director_prepare import REVIEW, Transport, ready, run  # noqa: F401

CASES = [
    ("director_candidate_rewrite", dict(wording_valid=False)),
    ("director_candidate_replan", dict(plan_valid=False)),
    ("director_no_valid_candidate", dict(wording_valid=False, safe_alternative=False)),
]


@pytest.mark.parametrize(("code", "review"), CASES)
async def test_preparation_stops_at_known_failure_and_keeps_attempts(
    agent_sessions,
    ready,  # noqa: F811
    code,
    review,
):
    transport = Transport(ready)
    transport.outputs[-1] = {**REVIEW, **review}
    with capture_logs() as logs:
        assert not await run(agent_sessions, ready, transport)
    assert transport.model_operations == ["plan", "review"]
    assert [item["error_code"] for item in logs if "error_code" in item] == [code]
    async with agent_sessions() as db:
        interview = await db.get(InterviewSession, ready["interview_id"])
        assert interview.status == "preparing_failed"
        assert interview.last_error["code"] == "first_question_failed"
        assert await db.scalar(select(func.count()).select_from(InterviewTurn)) == 0
        record = await db.scalar(select(LLMCallRecord).where(LLMCallRecord.task_name == "director"))
        assert record.turn_id is None and record.discard_reason is None
        assert record.failure["stage"] == "semantic" and record.failure["error_code"] == code
        assert len(record.attempts) == 2


@pytest.mark.parametrize(("code", "review"), CASES)
async def test_turn_failure_keeps_attempts_without_next_question_or_finish(
    agent_sessions, agent_seed, code, review
):
    from app.features.interview.director_service import process_answer

    await seed_turns(agent_sessions, agent_seed)
    sent = []

    async def handle(req):
        payload = json.loads(json.loads(req.content)["input"][0]["content"][0]["text"])
        sent.append(payload)
        if "answer" in payload:
            return response(asdict(analysis()))
        if payload["operation"] == "plan":
            return response(plan("tech_lead"))
        return response({**approved_review(), **review})

    options = dict(
        user_id=agent_seed["owner"],
        interview_id=agent_seed["interview_id"],
        turn_no=1,
        text="팀원 담당입니다",
        call_id=uuid4(),
        settings=settings(),
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        result = await process_answer(agent_sessions, **options, http_client=http)
        replay = await process_answer(agent_sessions, **options, http_client=http)
    assert recovery_code(result.failure) == code
    assert not result.completed and result.next_turn_id is None
    assert replay.failure == result.failure and replay.next_turn_id is None
    assert len(sent) == 3
    async with agent_sessions() as db:
        interview = await db.get(InterviewSession, agent_seed["interview_id"])
        assert interview.status == "in_progress" and interview.completed_at is None
        turns = (await db.scalars(select(InterviewTurn).order_by(InterviewTurn.turn_no))).all()
        assert [turn.turn_no for turn in turns] == [1]
        assert turns[-1].answer_text == "팀원 담당입니다"
        record = await db.scalar(select(LLMCallRecord).where(LLMCallRecord.task_name == "director"))
        assert record.turn_id is None and record.failure["error_code"] == code
        assert len(record.attempts) == 2
