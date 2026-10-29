"""알림 콜백의 예외·취소 정책과 허용 근거 범위의 내부 일치를 확인한다."""

import asyncio
from dataclasses import replace
from uuid import uuid4

import httpx
import pytest
from devon_ai import contracts as c
from sqlalchemy import select

from app.db.models import InterviewSession, InterviewTurn, LLMCallRecord
from app.features.interview.agent_context import AgentStateError
from tests.agents.test_director_runtime_service import analysis, seed_turns, settings


@pytest.mark.parametrize("turn_no", [1, 9])
@pytest.mark.parametrize("canceled", [False, True])
async def test_unexpected_notification_failure_preserves_answer_without_reexecuting_analysis(
    agent_sessions, agent_seed, turn_no, canceled
):
    from app.features.interview.director_service import process_answer

    await seed_turns(agent_sessions, agent_seed, turn_no)
    entered = asyncio.Event()

    async def notification():
        entered.set()
        if not canceled:
            raise ValueError("알림 콜백의 예상 밖 오류")
        await asyncio.Event().wait()

    async def provider(request):
        pytest.fail("종료된 답변 작업을 알림 오류나 재전송으로 다시 분석하면 안 된다")

    call_id = uuid4()
    options = dict(
        user_id=agent_seed["owner"],
        interview_id=agent_seed["interview_id"],
        turn_no=turn_no,
        text="팀원 담당입니다",
        settings=settings(),
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as http:
        task = asyncio.create_task(
            process_answer(
                agent_sessions,
                **options,
                call_id=call_id,
                http_client=http,
                on_answer_saved=notification,
            )
        )
        if canceled:
            await asyncio.wait_for(entered.wait(), 5)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            with pytest.raises(ValueError, match="알림 콜백의 예상 밖 오류"):
                await task
        replay = await process_answer(agent_sessions, **options, call_id=call_id, http_client=http)
        duplicate_id = uuid4()
        duplicate = await process_answer(
            agent_sessions, **options, call_id=duplicate_id, http_client=http
        )
    reason = "canceled" if canceled else "execution_error"
    assert replay.discard_reason == reason and not replay.accepted
    assert duplicate.discard_reason == "answer_already_saved" and not duplicate.accepted
    async with agent_sessions() as db:
        turn = await db.scalar(select(InterviewTurn).where(InterviewTurn.turn_no == turn_no))
        record = await db.get(LLMCallRecord, call_id)
        interview = await db.get(InterviewSession, agent_seed["interview_id"])
        assert turn.answer_text == "팀원 담당입니다" and turn.status == "answered"
        assert turn.analysis is None and turn.decision is None
        assert record.attempts == [] and record.discard_reason == reason
        assert await db.get(LLMCallRecord, duplicate_id) is None
        assert interview.status == "in_progress" and interview.completed_at is None


async def test_missing_verified_scope_is_rejected_before_provider_io(agent_sessions, agent_seed):
    from app.features.interview.answer_context import load_answer_context
    from app.features.interview.director_service import _retrieve

    await seed_turns(agent_sessions, agent_seed)
    async with agent_sessions() as db:
        loaded = await load_answer_context(
            db,
            user_id=agent_seed["owner"],
            interview_id=agent_seed["interview_id"],
            turn_no=1,
            limits=c.ContextLimits(2, 0, "test"),
        )
    request = c.VerificationRequest(
        "팀원 담당입니다",
        "구현 확인",
        str(agent_seed["repo_id"]),
        agent_seed["sha"],
        ("src/main.py",),
    )
    locations = frozenset({(request.repository_id, request.git_ref, "src/main.py")})
    checked = c.validate_analysis(
        replace(analysis(), needs_verification=True, verification_requests=(request,)),
        question=loaded.question,
        answer_text="팀원 담당입니다",
        evidence_refs=frozenset(),
        allowed_locations=locations,
    )

    async def provider(request):
        pytest.fail("누락된 허용 scope를 원격 조회로 복구하면 안 된다")

    async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as http:
        with pytest.raises(AgentStateError, match="evidence_scope_invalid"):
            await _retrieve(
                agent_sessions,
                agent_seed["owner"],
                agent_seed["interview_id"],
                loaded.context,
                checked,
                locations,
                [],
                None,
                http,
                None,
            )
