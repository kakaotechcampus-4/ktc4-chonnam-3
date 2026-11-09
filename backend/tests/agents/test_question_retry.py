"""명시 질문 복구는 답변·분석을 재생하지 않고 다음 질문만 확정한다."""

import asyncio
from copy import deepcopy
from dataclasses import asdict
from uuid import uuid4

import httpx
import pytest
from redis.exceptions import RedisError
from sqlalchemy import select

from app.core.errors import AppError
from app.db.models import InterviewSession, InterviewTurn, LLMCallRecord, User
from tests.agents.director_helpers import (
    analysis,
    approved_review,
    plan,
    response,
    seed_turns,
    settings,
)


class Redis:
    def __init__(self):
        self.calls = []
        self.fail = False

    async def eval(self, script, count, *args):
        if self.fail:
            raise RedisError("fixture")
        self.calls.append(args)
        return 1


async def failed_question(sessions, seed):
    await seed_turns(sessions, seed)
    async with sessions.begin() as db:
        turn = await db.scalar(
            select(InterviewTurn).where(InterviewTurn.interview_session_id == seed["interview_id"])
        )
        turn.status = "answered"
        turn.answer_text = "팀원 담당입니다"
        turn.analysis = asdict(analysis())
        prior = LLMCallRecord(
            interview_session_id=seed["interview_id"],
            turn_id=turn.id,
            turn_no=1,
            task_name="answer_analysis",
            attempts=[{"error_stage": None}],
        )
        failed = LLMCallRecord(
            interview_session_id=seed["interview_id"],
            turn_no=2,
            task_name="director",
            failure={
                "stage": "semantic",
                "error_code": "director_candidate_rewrite",
                "reason_summary": "Independent question review rejected.",
            },
            attempts=[],
        )
        db.add_all([prior, failed])
        await db.flush()
        return turn.id, failed.id


async def retry(sessions, seed, redis, request_id, http):
    from app.features.interview.question_retry import retry_question

    return await retry_question(
        sessions,
        redis,
        user_id=seed["owner"],
        interview_id=seed["interview_id"],
        request_id=request_id,
        settings=settings(),
        http_client=http,
    )


async def test_manual_retry_preserves_answer_analysis_and_failure_and_replays_without_calls(
    agent_sessions, agent_seed
):
    turn_id, failure_id = await failed_question(agent_sessions, agent_seed)
    sent = []

    async def handler(req):
        import json

        payload = json.loads(json.loads(req.content)["input"][0]["content"][0]["text"])
        sent.append(payload)
        return response(
            approved_review() if payload["operation"] == "review" else plan("tech_lead")
        )

    request_id, redis = uuid4(), Redis()
    async with agent_sessions() as db:
        old = await db.get(InterviewTurn, turn_id)
        before = (old.answer_text, deepcopy(old.analysis))
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        first = await retry(agent_sessions, agent_seed, redis, request_id, http)
        again = await retry(agent_sessions, agent_seed, redis, request_id, http)
    assert first == again and first.turn_no == 2
    assert len(sent) == 2 and {item["operation"] for item in sent} == {"plan", "review"}
    async with agent_sessions() as db:
        old = await db.get(InterviewTurn, turn_id)
        failed = await db.get(LLMCallRecord, failure_id)
        assert (old.answer_text, old.analysis) == before
        assert failed.failure["error_code"] == "director_candidate_rewrite"
        assert failed.turn_id is None and failed.attempts == []
        turns = list(await db.scalars(select(InterviewTurn).order_by(InterviewTurn.turn_no)))
        assert len(turns) == 2 and turns[1].status == "asked"


async def test_rejected_manual_retry_is_cached_and_manual_limit_is_one(agent_sessions, agent_seed):
    await failed_question(agent_sessions, agent_seed)
    calls = []

    async def handler(req):
        calls.append(req)
        return response(
            plan("tech_lead") if len(calls) == 1 else {**approved_review(), "wording_valid": False}
        )

    request_id, redis = uuid4(), Redis()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        for expected, rid in [
            ("question_retry_failed", request_id),
            ("question_retry_failed", request_id),
            ("question_retry_limit", uuid4()),
        ]:
            with pytest.raises(AppError) as error:
                await retry(agent_sessions, agent_seed, redis, rid, http)
            assert error.value.reason.value == expected
    assert len(calls) == 2


async def test_concurrent_requests_only_reserve_one_round(agent_sessions, agent_seed):
    await failed_question(agent_sessions, agent_seed)
    entered, release = asyncio.Event(), asyncio.Event()
    count = 0

    async def handler(req):
        nonlocal count
        count += 1
        if count == 1:
            entered.set()
            await release.wait()
            return response(plan("tech_lead"))
        return response(approved_review())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        running = asyncio.create_task(retry(agent_sessions, agent_seed, Redis(), uuid4(), http))
        await asyncio.wait_for(entered.wait(), 5)
        try:
            with pytest.raises(AppError) as error:
                await retry(agent_sessions, agent_seed, Redis(), uuid4(), http)
            assert error.value.reason.value == "question_retry_in_progress"
        finally:
            release.set()
        await running
    assert count == 2


async def test_redis_failure_after_question_storage_never_regenerates(agent_sessions, agent_seed):
    await failed_question(agent_sessions, agent_seed)
    calls = []

    async def handler(req):
        calls.append(req)
        return response(plan("tech_lead") if len(calls) == 1 else approved_review())

    redis, request_id = Redis(), uuid4()
    redis.fail = True
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(AppError):
            await retry(agent_sessions, agent_seed, redis, request_id, http)
        redis.fail = False
        result = await retry(agent_sessions, agent_seed, redis, request_id, http)
    assert result.turn_no == 2 and len(calls) == 2


@pytest.mark.parametrize("change", ["no_analysis", "inactive", "abandoned", "foreign"])
async def test_ineligible_states_never_call_model(agent_sessions, agent_seed, change):
    turn_id, _ = await failed_question(agent_sessions, agent_seed)
    async with agent_sessions.begin() as db:
        if change == "no_analysis":
            (await db.get(InterviewTurn, turn_id)).analysis = None
        elif change == "inactive":
            (await db.get(User, agent_seed["owner"])).status = "suspended"
        elif change == "abandoned":
            (await db.get(InterviewSession, agent_seed["interview_id"])).status = "abandoned"
        else:
            agent_seed["owner"] = agent_seed["other"]

    async def forbidden(req):
        pytest.fail("ineligible retry reached the provider")

    async with httpx.AsyncClient(transport=httpx.MockTransport(forbidden)) as http:
        with pytest.raises(AppError):
            await retry(agent_sessions, agent_seed, Redis(), uuid4(), http)


async def test_request_cancellation_does_not_repeat_or_cancel_started_generation(
    agent_sessions, agent_seed
):
    from app.features.interview import question_retry

    await failed_question(agent_sessions, agent_seed)
    entered, release = asyncio.Event(), asyncio.Event()
    calls, request_id, redis = [], uuid4(), Redis()

    async def handler(req):
        calls.append(req)
        if len(calls) == 1:
            entered.set()
            await release.wait()
            return response(plan("tech_lead"))
        return response(approved_review())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        caller = asyncio.create_task(retry(agent_sessions, agent_seed, redis, request_id, http))
        await asyncio.wait_for(entered.wait(), 5)
        caller.cancel()
        with pytest.raises(asyncio.CancelledError):
            await caller
        release.set()
        await asyncio.wait_for(asyncio.gather(*tuple(question_retry._RUNNING)), 10)
        result = await retry(agent_sessions, agent_seed, redis, request_id, http)
    assert result.turn_no == 2 and len(calls) == 2


@pytest.mark.parametrize("change", ["abandon", "deadline", "binding"])
async def test_late_result_is_not_published_after_scope_changes(agent_sessions, agent_seed, change):
    from datetime import UTC, datetime, timedelta

    turn_id, _ = await failed_question(agent_sessions, agent_seed)
    calls = []

    async def handler(req):
        calls.append(req)
        if len(calls) == 1:
            async with agent_sessions.begin() as db:
                row = await db.get(InterviewSession, agent_seed["interview_id"])
                if change == "abandon":
                    row.status = "abandoned"
                elif change == "deadline":
                    state = deepcopy(row.context_state)
                    for entry in state["question_retry_v1"].values():
                        entry["deadline"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
                    row.context_state = state
                else:
                    (await db.get(InterviewTurn, turn_id)).answer_text += " 변경"
            return response(plan("tech_lead"))
        return response(approved_review())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(AppError) as error:
            await retry(agent_sessions, agent_seed, Redis(), uuid4(), http)
        assert error.value.reason.value == "question_retry_failed"
    async with agent_sessions() as db:
        assert len(list(await db.scalars(select(InterviewTurn)))) == 1
    assert len(calls) == 2
