"""답변 수명 종료가 실제 PG의 자동 복구·외부 조회 정리를 기다린다."""

import asyncio
import json
from dataclasses import asdict, replace

import httpx
import pytest
from devon_ai import contracts as c
from pydantic import SecretStr
from sqlalchemy import select

from app.db.models import InterviewSession, InterviewTurn, LLMCallRecord, PromptVersion
from app.features.interview import external_knowledge, question_retry, ws
from app.features.interview.agent_context import AgentStateError
from app.integrations.search.tavily import TavilyClient
from tests.agents.director_helpers import analysis, approved_review, plan, response, seed_turns
from tests.features.interview.test_ws_work_lifetime import WorkRedis, connection


@pytest.mark.parametrize("phase", ["automatic_rewrite", "external_lookup"])
@pytest.mark.parametrize("stop", ["deadline", "cancel"])
async def test_answer_lifetime_joins_real_claim_ledger_and_reservation_cleanup(
    agent_sessions, agent_seed, monkeypatch, phase, stop
):
    await seed_turns(agent_sessions, agent_seed)
    async with agent_sessions.begin() as db:
        for prompt in await db.scalars(select(PromptVersion)):
            prompt.version = (
                "director_v7" if prompt.task_name == "director" else "answer_analysis_v2"
            )
    entered = asyncio.Event()
    calls = []

    async def assert_settled():
        async with agent_sessions() as db:
            interview = await db.get(InterviewSession, agent_seed["interview_id"])
            state = interview.context_state
            assert state.get("external_search_reservations", {}) == {}
            ledger = state.get("question_retry_v1", {})
            assert all(entry["status"] != "running" for entry in ledger.values())
            if phase == "automatic_rewrite":
                assert len(ledger) == 1
                assert next(iter(ledger.values()))["status"] == "failed"
            pending = await db.scalar(
                select(LLMCallRecord.id).where(
                    LLMCallRecord.turn_id.is_(None),
                    LLMCallRecord.failure.is_(None),
                    LLMCallRecord.discard_reason.is_(None),
                )
            )
            assert pending is None and not question_retry._RUNNING
            turn = await db.scalar(select(InterviewTurn).where(InterviewTurn.turn_no == 1))
            assert turn.status == "answered" and turn.answer_text == "팀원 담당입니다"

    class CheckedRedis(WorkRedis):
        async def execute_command(self, command, script, count, *args):
            if script == ws._RELEASE:
                await assert_settled()
            return await super().execute_command(command, script, count, *args)

    old = connection(CheckedRedis())
    config = old.socket.app.state.settings
    config.tavily_api_key = SecretStr("fixture")
    old.socket.app.state.session_factory = agent_sessions
    old.interview_id = agent_seed["interview_id"]

    async def noop(*args):
        pass

    old.answer_saved = old.evidence_checked = noop

    async def read_state(*args):
        return ws._State("in_progress", {"turn": 1}, {}, None, (), "text")

    async def provider(request):
        if request.url.path == "/search":
            calls.append("external_search")
            entered.set()
            await asyncio.Event().wait()
        payload = json.loads(json.loads(request.content)["input"][0]["content"][0]["text"])
        operation = payload.get("operation", "analysis")
        calls.append(operation)
        if operation == "analysis":
            result = analysis()
            if phase == "external_lookup":
                result = replace(
                    result,
                    needs_verification=True,
                    external_queries=(c.ExternalQueryRequest("Redis sessions", "일반 개념 보완"),),
                )
            return response(asdict(result))
        if operation == "plan":
            if calls.count("plan") == 2:
                entered.set()
                await asyncio.Event().wait()
            return response(plan("tech_lead"))
        return response({**approved_review(), "wording_valid": False})

    monkeypatch.setattr(ws, "_read_state", read_state)
    monkeypatch.setattr(ws, "_answer_work_seconds", lambda *args: 5)
    monkeypatch.setattr(
        external_knowledge,
        "TavilyClient",
        lambda settings: TavilyClient(settings, transport=httpx.MockTransport(provider)),
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as http:
        old.socket.app.state.http_client = http
        running = asyncio.create_task(
            ws._execute(old, agent_seed["owner"], 1, "팀원 담당입니다", answer_mode="text")
        )
        try:
            await asyncio.wait_for(entered.wait(), 4)
            if stop == "cancel":
                running.cancel()
            expected = AgentStateError if stop == "deadline" else asyncio.CancelledError
            with pytest.raises(expected):
                await running
        finally:
            running.cancel()
            await asyncio.gather(running, return_exceptions=True)
    await assert_settled()
    assert old.redis.owner is None
    assert calls == (
        ["analysis", "plan", "review", "plan"]
        if phase == "automatic_rewrite"
        else ["analysis", "external_search"]
    )
