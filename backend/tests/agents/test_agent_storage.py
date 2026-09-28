"""실제 DB와 HTTP mock으로 질문·계약·호출 기록의 한 트랜잭션 저장을 검증한다."""

import asyncio
import json
from dataclasses import asdict, replace
from uuid import uuid4

import httpx
import pytest
from devon_ai import contracts as c
from sqlalchemy import event, func, select, update

from app.core.config import Settings
from app.db.models import (
    Evidence,
    InterviewSession,
    InterviewTurn,
    LLMCallRecord,
    SessionRepository,
    TurnEvidence,
)
from app.integrations.llm.client import CallBudget


def prepared_contract():
    return c.QuestionContract(
        "본인 역할 소개", (c.RequiredPoint("role", "본인 역할"),), (), (), "역할"
    )


def output():
    return json.dumps(
        dict(
            persona="hr_manager",
            text="본인 역할을 소개해 주세요.",
            topic_code="role",
            evidence_refs=[],
            jd_requirement_ids=[],
        )
    )


def response(raw):
    return httpx.Response(
        200,
        json={
            "id": "fixture-response",
            "model": "actual-model",
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "status": "completed",
                    "content": [{"type": "output_text", "text": raw}],
                }
            ],
            "usage": {"input_tokens": 11, "output_tokens": 7},
        },
    )


async def invoke(
    agent_sessions, agent_seed, http, *, call_id=None, user_id=None, reviewer=None, contract=None
):
    from app.features.interview import agent_service

    contract = contract or prepared_contract()

    async def review(request, question):
        return c.QuestionReview(question.text, contract)

    return await agent_service.generate_prepared_question(
        agent_sessions,
        user_id=user_id or agent_seed["owner"],
        interview_id=agent_seed["interview_id"],
        call_id=call_id or uuid4(),
        question_contract=contract,
        review=reviewer or review,
        settings=Settings(
            _env_file=None,
            openai_api_key="private-key",
            llm_timeout_seconds=5,
            llm_max_output_tokens=128,
            llm_max_input_bytes=65536,
            llm_max_response_bytes=65536,
        ).require_llm(),
        limits=c.ContextLimits(2, 0, "fixture"),
        budget=CallBudget(),
        http_client=http,
    )


async def test_question_contract_and_metadata_are_durable_and_replay_does_not_call_model(
    agent_sessions,
    agent_seed,
):
    sent = []

    async def transport(request):
        sent.append(json.loads(request.content))
        # 모델을 기다리는 동안 면접 행 잠금이 열려 있어야 한다.
        async with agent_sessions.begin() as db:
            await db.execute(select(InterviewSession).with_for_update(nowait=True))
        return response(output())

    call_id = uuid4()
    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as http:
        result = await invoke(agent_sessions, agent_seed, http, call_id=call_id)
        replay = await invoke(agent_sessions, agent_seed, http, call_id=call_id)
    assert result.turn_id == replay.turn_id and result.turn_id is not None
    assert result.failure is None and result.discard_reason is None
    assert len(sent) == 1 and sent[0]["model"] == "db-model"
    async with agent_sessions() as db:
        turn = await db.get(InterviewTurn, result.turn_id)
        record = await db.get(LLMCallRecord, call_id)
        assert turn.question_contract == json.loads(json.dumps(asdict(prepared_contract())))
        assert record.turn_id == turn.id and record.task_name == "director"
        assert record.attempts[0]["raw_output"] == output()
        assert record.attempts[0]["model"] == turn.model == "actual-model"
        assert record.attempts[0]["input_tokens"] == 11
        assert record.attempts[0]["prompt_version"] == turn.prompt_version == "director_v1"
        assert (await db.get(InterviewSession, agent_seed["interview_id"])).current_turn == 1
    assert "private-key" not in repr(result) and output() not in repr(result)


async def test_failed_parse_keeps_both_attempts_without_creating_question(
    agent_sessions, agent_seed
):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: response("not-json"))
    ) as http:
        result = await invoke(agent_sessions, agent_seed, http)
    assert result.turn_id is None and result.failure.stage == "parse"
    async with agent_sessions() as db:
        assert await db.scalar(select(func.count()).select_from(InterviewTurn)) == 0
        record = await db.get(LLMCallRecord, result.call_id)
        assert [item["attempt"] for item in record.attempts] == [1, 2]
        assert record.failure["stage"] == "parse"


async def test_late_model_result_is_recorded_but_never_creates_question(agent_sessions, agent_seed):
    async def transport(request):
        async with agent_sessions.begin() as db:
            await db.execute(update(InterviewSession).values(status="abandoned"))
        return response(output())

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as http:
        result = await invoke(agent_sessions, agent_seed, http)
    assert result.turn_id is None and result.discard_reason == "context_changed"
    assert result.failure is None  # 모델 성공과 상태가 바뀌어 폐기된 결과는 구별한다.
    async with agent_sessions() as db:
        record = await db.get(LLMCallRecord, result.call_id)
        assert len(record.attempts) == 1 and record.discard_reason == "context_changed"
        assert await db.scalar(select(func.count()).select_from(InterviewTurn)) == 0


async def test_question_evidence_is_linked_in_the_same_transaction(agent_sessions, agent_seed):
    evidence_id = uuid4()
    async with agent_sessions.begin() as db:
        db.add(
            Evidence(
                id=evidence_id,
                interview_session_id=agent_seed["interview_id"],
                repository_id=agent_seed["repo_id"],
                git_ref=agent_seed["sha"],
                source_type="file",
                path="src/main.py",
                snippet="example",
                tool_name="read_file",
                start_line=1,
                end_line=1,
            )
        )
    contract = replace(prepared_contract(), basis_refs=(c.BasisRef("evidence", str(evidence_id)),))
    candidate = json.loads(output())
    candidate["evidence_refs"] = [str(evidence_id)]
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: response(json.dumps(candidate)))
    ) as http:
        result = await invoke(agent_sessions, agent_seed, http, contract=contract)
    assert result.turn_id is not None
    async with agent_sessions() as db:
        link = (await db.scalars(select(TurnEvidence))).one()
        assert (link.turn_id, link.evidence_id, link.usage) == (
            result.turn_id,
            evidence_id,
            "question_basis",
        )


async def test_unavailable_posting_body_is_rejected_without_fabricating_source(
    agent_sessions, agent_seed
):
    async with agent_sessions() as db:
        posting_id = (await db.get(InterviewSession, agent_seed["interview_id"])).job_posting_id
    contract = replace(
        prepared_contract(), basis_refs=(c.BasisRef("job_posting", str(posting_id)),)
    )

    def forbidden(request):
        pytest.fail("missing source reached provider")

    async with httpx.AsyncClient(transport=httpx.MockTransport(forbidden)) as http:
        result = await invoke(agent_sessions, agent_seed, http, contract=contract)
    assert result.failure.error_code == "director_input_invalid" and result.turn_id is None
    async with agent_sessions() as db:
        assert (await db.get(LLMCallRecord, result.call_id)).attempts == []


async def test_first_failed_attempt_survives_cancellation_during_retry(agent_sessions, agent_seed):
    retry_started = asyncio.Event()
    sent = 0

    async def transport(request):
        nonlocal sent
        sent += 1
        if sent == 1:
            return response("not-json")
        retry_started.set()
        await asyncio.Event().wait()

    call_id = uuid4()
    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as http:
        running = asyncio.create_task(invoke(agent_sessions, agent_seed, http, call_id=call_id))
        try:
            await asyncio.wait_for(retry_started.wait(), timeout=5)
        finally:
            running.cancel()
            with pytest.raises(asyncio.CancelledError):
                await running
    async with agent_sessions() as db:
        record = await db.get(LLMCallRecord, call_id)
        assert record.discard_reason == "canceled"
        assert len(record.attempts) == 1
        assert record.attempts[0]["attempt"] == 1
        assert record.attempts[0]["raw_output"] == "not-json"
        assert record.turn_id is None and record.failure is None


@pytest.mark.parametrize("invalid", ["owner", "snapshot"])
async def test_untrusted_scope_never_reaches_provider(agent_sessions, agent_seed, invalid):
    from app.features.interview.agent_context import AgentStateError

    if invalid == "snapshot":
        async with agent_sessions.begin() as db:
            await db.execute(update(SessionRepository).values(snapshot_head_sha=None))

    def forbidden(request):
        pytest.fail("invalid state reached HTTP")

    async with httpx.AsyncClient(transport=httpx.MockTransport(forbidden)) as http:
        with pytest.raises(AgentStateError):
            await invoke(
                agent_sessions,
                agent_seed,
                http,
                user_id=agent_seed["other"] if invalid == "owner" else None,
            )
    async with agent_sessions() as db:
        assert await db.scalar(select(func.count()).select_from(LLMCallRecord)) == 0


async def test_pending_generation_blocks_duplicates_and_cancellation_releases_claim(
    agent_sessions,
    agent_seed,
):
    from app.features.interview.agent_context import AgentStateError

    entered = asyncio.Event()

    async def transport(request):
        entered.set()
        await asyncio.Event().wait()

    call_id = uuid4()
    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as http:
        running = asyncio.create_task(invoke(agent_sessions, agent_seed, http, call_id=call_id))
        try:
            await asyncio.wait_for(entered.wait(), timeout=5)
            with pytest.raises(AgentStateError, match="call_in_progress"):
                await invoke(agent_sessions, agent_seed, http)
        finally:
            running.cancel()
            with pytest.raises(asyncio.CancelledError):
                await running
    async with agent_sessions() as db:
        record = await db.get(LLMCallRecord, call_id)
        assert record.discard_reason == "canceled" and record.turn_id is None
        assert record.failure is None
        assert await db.scalar(select(func.count()).select_from(LLMCallRecord)) == 1
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: response(output()))
    ) as http:
        retried = await invoke(agent_sessions, agent_seed, http)
    assert retried.turn_id is not None
