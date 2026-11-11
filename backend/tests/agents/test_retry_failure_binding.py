"""v12 복구 예약 뒤 원래 실패 기록이 바뀌면 추가 호출과 질문 확정을 막는다."""

import json
from copy import deepcopy
from dataclasses import asdict
from uuid import uuid4, uuid5

import httpx
import pytest
from sqlalchemy import select

from app.db.models import InterviewSession, InterviewTurn, LLMCallRecord
from app.features.interview import question_retry
from tests.agents.director_helpers import analysis, approved_review, plan, response
from tests.agents.test_auto_replan import answer, payload, seed


async def mutate(sessions, failed_id, change):
    async with sessions.begin() as db:
        record = await db.get(LLMCallRecord, failed_id)
        if change == "failure":
            record.failure = {**record.failure, "reason_summary": "원래 실패 설명 변경"}
        else:
            attempts = deepcopy(record.attempts)
            if change == "raw":
                review = json.loads(attempts[-1]["raw_output"])
                review["safe_alternative"] = False
                attempts[-1]["raw_output"] = json.dumps(review, ensure_ascii=False)
            else:
                attempts[0]["input_tokens"] += 1
            record.attempts = attempts


@pytest.mark.parametrize("kind", ["rewrite", "replan"])
@pytest.mark.parametrize("phase", ["before_execute", "during_model_io"])
@pytest.mark.parametrize("change", ["raw", "failure", "attempt_metadata"])
async def test_reserved_v12_failure_identity_is_checked_before_io_and_before_commit(
    agent_sessions, agent_seed, monkeypatch, kind, phase, change
):
    await seed(agent_sessions, agent_seed)
    sent, reviews, changed, call_id = [], 0, False, uuid4()
    failed_id = uuid5(call_id, "director")
    original_run = question_retry._run

    async def change_before_execute(sessions, **kwargs):
        nonlocal changed
        await mutate(sessions, failed_id, change)
        changed = True
        return await original_run(sessions, **kwargs)

    if phase == "before_execute":
        monkeypatch.setattr(question_retry, "_run", change_before_execute)

    async def handle(request):
        nonlocal reviews, changed
        item = payload(request)
        sent.append(item)
        if "answer" in item:
            return response(asdict(analysis()))
        if item["operation"] == "plan":
            if reviews:
                await mutate(agent_sessions, failed_id, change)
                changed = True
            return response(plan("tech_lead"))
        reviews += 1
        return response(
            {**approved_review(), "wording_valid" if kind == "rewrite" else "plan_valid": False}
            if reviews == 1
            else approved_review()
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        result = await answer(agent_sessions, agent_seed, http, call_id=call_id)
    assert changed and len(sent) == (3 if phase == "before_execute" else 5)
    assert result.next_turn_id is None
    async with agent_sessions() as db:
        row = await db.get(InterviewSession, agent_seed["interview_id"])
        entry = next(iter(row.context_state["question_retry_v1"].values()))
        assert entry["failed_call_id"] == str(failed_id)
        assert len(entry["failure_binding"]) == 64
        assert "safe_alternative" not in json.dumps(entry)
        assert entry["status"] == "failed"
        assert len(list(await db.scalars(select(InterviewTurn)))) == 1


async def test_legacy_auto_entry_does_not_gain_a_new_failure_binding(agent_sessions, agent_seed):
    await seed(agent_sessions, agent_seed, "director_v10")
    sent, reviews, call_id = [], 0, uuid4()

    async def handle(request):
        nonlocal reviews
        item = payload(request)
        sent.append(item)
        if "answer" in item:
            return response(asdict(analysis()))
        if item["operation"] == "plan":
            if reviews:
                await mutate(agent_sessions, uuid5(call_id, "director"), "failure")
            return response(plan("tech_lead"))
        reviews += 1
        return response({**approved_review(), "wording_valid": reviews > 1})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        result = await answer(agent_sessions, agent_seed, http, call_id=call_id)
    assert result.next_turn_id is not None and len(sent) == 5
    async with agent_sessions() as db:
        row = await db.get(InterviewSession, agent_seed["interview_id"])
        entry = next(iter(row.context_state["question_retry_v1"].values()))
        assert "failure_binding" not in entry
