"""자동 Director는 실제 PostgreSQL 상태와 HTTP 공급자 경계를 함께 사용한다."""

import asyncio
import json
from dataclasses import asdict, replace
from uuid import uuid4

import httpx
import pytest
from devon_ai import contracts as c
from sqlalchemy import select

from app.core.config import Settings
from app.db.models import (
    Evidence,
    EvidenceConflict,
    InterviewSession,
    InterviewTurn,
    JobPosting,
    LLMCallRecord,
    PromptVersion,
    TurnEvidence,
)


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


async def test_answer_loader_keeps_current_turn_outside_history_even_at_nine(
    agent_sessions, agent_seed
):
    from app.features.interview.answer_context import load_answer_context

    await seed_turns(agent_sessions, agent_seed, 9)
    async with agent_sessions() as db:
        loaded = await load_answer_context(
            db,
            user_id=agent_seed["owner"],
            interview_id=agent_seed["interview_id"],
            turn_no=9,
            limits=c.ContextLimits(2, 0, "test"),
        )
    assert loaded.context.turn_no == 9
    assert len(loaded.context.history) == 8
    assert loaded.context.current_turn_id == loaded.turn_id
    assert all(turn.turn_id != loaded.turn_id for turn in loaded.context.history)
    assert loaded.question.data.question_contract == contract()
    assert loaded.context.allowed_personas == ("domain_lead",)


async def test_last_answer_is_analyzed_before_completion_and_replay_never_calls_again(
    agent_sessions, agent_seed
):
    from app.features.interview.director_service import process_answer

    await seed_turns(agent_sessions, agent_seed, 9)
    sent, acknowledged = [], []

    async def handle(request):
        sent.append(request)
        async with agent_sessions.begin() as db:
            interview = await db.scalar(select(InterviewSession).with_for_update(nowait=True))
            assert interview.status == "in_progress"
        assert acknowledged == [True]
        return response(asdict(analysis()))

    async def acknowledge():
        acknowledged.append(True)

    call_id = uuid4()
    options = dict(
        user_id=agent_seed["owner"],
        interview_id=agent_seed["interview_id"],
        turn_no=9,
        text="팀원 담당입니다",
        call_id=call_id,
        settings=settings(),
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        result = await process_answer(
            agent_sessions, **options, http_client=http, on_answer_saved=acknowledge
        )
        replay = await process_answer(
            agent_sessions, **options, http_client=http, on_answer_saved=acknowledge
        )
    assert result.completed and result.next_turn_id is None and result.failure is None
    assert result.accepted and not replay.accepted
    assert len(sent) == len(acknowledged) == 1
    async with agent_sessions() as db:
        interview = await db.get(InterviewSession, agent_seed["interview_id"])
        turn = await db.get(InterviewTurn, result.turn_id)
        record = await db.get(LLMCallRecord, call_id)
        assert interview.status == "completed" and interview.completed_at is not None
        assert interview.context_state["director"]["phase"] == "completed"
        assert interview.context_state["director"]["current_turn_id"] == str(turn.id)
        assert turn.analysis == json.loads(json.dumps(asdict(analysis())))
        assert turn.decision["next_step"] == "finish"
        assert record.task_name == "answer_analysis" and len(record.attempts) == 1


async def test_analysis_failure_preserves_answer_and_does_not_complete(agent_sessions, agent_seed):
    from app.features.interview.director_service import process_answer

    await seed_turns(agent_sessions, agent_seed, 9)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: response({"invalid": True}))
    ) as http:
        result = await process_answer(
            agent_sessions,
            user_id=agent_seed["owner"],
            interview_id=agent_seed["interview_id"],
            turn_no=9,
            text="팀원 담당입니다",
            call_id=uuid4(),
            settings=settings(),
            http_client=http,
        )
    assert result.failure.stage == "schema" and not result.completed
    async with agent_sessions() as db:
        turn = await db.get(InterviewTurn, result.turn_id)
        assert turn.status == "answered" and turn.answer_text == "팀원 담당입니다"
        assert turn.analysis is None
        assert (await db.get(InterviewSession, agent_seed["interview_id"])).status == "in_progress"


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


async def test_all_nine_answers_use_analysis_then_independent_director_review(
    agent_sessions, agent_seed
):
    from app.features.interview.director_service import process_answer, start_director

    await seed_turns(agent_sessions, agent_seed, 0)
    sent = []

    async def handle(request):
        body = json.loads(request.content)
        payload = json.loads(body["input"][0]["content"][0]["text"])
        sent.append(payload)
        async with agent_sessions.begin() as db:
            await db.execute(select(InterviewSession).with_for_update(nowait=True))
        if "answer" in payload:
            assert payload["answer"]["turn_id"] not in {
                turn["turn_id"] for turn in payload["history"]
            }
            return response(asdict(analysis()), "analysis-model")
        if payload["operation"] == "review":
            assert "reason_summary" not in payload
            return response(approved_review(), "review-model")
        persona = payload["context"]["allowed_personas"][0]
        if payload["context"]["turn_no"] > 1:
            assert payload["prior_analyses"]
            assert payload["answer_analysis"]["contribution_scope"]["scope"] == "teammate"
        return response(plan(persona), "generation-model")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        first = await start_director(
            agent_sessions,
            user_id=agent_seed["owner"],
            interview_id=agent_seed["interview_id"],
            call_id=uuid4(),
            settings=settings(),
            http_client=http,
        )
        assert first.turn_id is not None
        for turn_no in range(1, 10):
            result = await process_answer(
                agent_sessions,
                user_id=agent_seed["owner"],
                interview_id=agent_seed["interview_id"],
                turn_no=turn_no,
                text="팀원 담당입니다",
                call_id=uuid4(),
                settings=settings(),
                http_client=http,
            )
            assert result.failure is None and result.discard_reason is None
            assert result.completed is (turn_no == 9)
    assert len(sent) == 27
    async with agent_sessions() as db:
        turns = list(await db.scalars(select(InterviewTurn).order_by(InterviewTurn.turn_no)))
        assert len(turns) == 9 and all(turn.analysis is not None for turn in turns)
        assert [turn.persona for turn in turns].count("hr_manager") == 1
        assert [turn.persona for turn in turns].count("tech_lead") == 6
        assert [turn.persona for turn in turns].count("domain_lead") == 2
        assert all(turn.model == "generation-model" for turn in turns)


async def test_lookup_failure_is_recorded_and_delivered_to_director_without_false_claim(
    agent_sessions, agent_seed
):
    from app.features.interview.director_service import process_answer

    await seed_turns(agent_sessions, agent_seed)
    request = c.VerificationRequest(
        "팀원 담당입니다",
        "해당 파일의 구현 확인",
        str(agent_seed["repo_id"]),
        agent_seed["sha"],
        ("src/main.py",),
    )
    original = replace(analysis(), needs_verification=True, verification_requests=(request,))
    sent, checks = [], []

    async def handle(req):
        if req.url.host == "api.github.com":
            assert checks == []
            return httpx.Response(500)
        body = json.loads(req.content)
        payload = json.loads(body["input"][0]["content"][0]["text"])
        sent.append(payload)
        if "answer" in payload:
            return response(asdict(original if not payload["tool_results"] else analysis()))
        assert payload["tool_results"][0]["status"] == "tool_error"
        return response(plan("tech_lead") if payload["operation"] == "plan" else approved_review())

    async def check(value):
        checks.append(value)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        result = await process_answer(
            agent_sessions,
            user_id=agent_seed["owner"],
            interview_id=agent_seed["interview_id"],
            turn_no=1,
            text="팀원 담당입니다",
            call_id=uuid4(),
            settings=settings(),
            http_client=http,
            on_evidence_check=check,
        )
    assert result.next_turn_id is not None and result.failure is None
    assert len(sent) == 4
    async with agent_sessions() as db:
        turn = await db.get(InterviewTurn, result.turn_id)
        assert turn.analysis == json.loads(json.dumps(asdict(original)))
        assert "tool_error" in turn.decision["reason_summary"]
        record = await db.get(LLMCallRecord, result.call_id)
        assert len(record.attempts) == 2


async def test_cancel_during_lookup_preserves_first_analysis_and_records_requested_scope(
    agent_sessions, agent_seed
):
    from app.features.interview.director_service import process_answer

    await seed_turns(agent_sessions, agent_seed)
    request = c.VerificationRequest(
        "팀원 담당입니다",
        "구현 확인",
        str(agent_seed["repo_id"]),
        agent_seed["sha"],
        ("src/main.py",),
    )
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
                snippet="원문 근거",
                tool_name="read_file",
            )
        )
    original = replace(
        analysis(),
        needs_verification=True,
        verification_requests=(request,),
        technical_assessment=c.TechnicalAssessment(
            "한정된 원문 검토", (), (str(evidence_id),), ("추가 조건 확인",)
        ),
    )
    entered = asyncio.Event()

    async def handle(req):
        if req.url.host == "api.github.com":
            entered.set()
            await asyncio.Event().wait()
        return response(asdict(original))

    call_id = uuid4()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        task = asyncio.create_task(
            process_answer(
                agent_sessions,
                user_id=agent_seed["owner"],
                interview_id=agent_seed["interview_id"],
                turn_no=1,
                text="팀원 담당입니다",
                call_id=call_id,
                settings=settings(),
                http_client=http,
            )
        )
        await asyncio.wait_for(entered.wait(), 5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    async with agent_sessions() as db:
        turn = await db.scalar(select(InterviewTurn).where(InterviewTurn.turn_no == 1))
        assert turn.analysis == json.loads(json.dumps(asdict(original)))
        assert turn.decision["next_step"] == "retrieve"
        assert (
            "중단" in turn.decision["reason_summary"]
            and "src/main.py" in turn.decision["reason_summary"]
        )
        record = await db.get(LLMCallRecord, call_id)
        assert record.discard_reason == "canceled" and len(record.attempts) == 1
        link = (await db.scalars(select(TurnEvidence))).one()
        assert link.evidence_id == evidence_id and link.usage == "evaluation_basis"


async def test_replay_during_tool_phase_is_still_in_progress(agent_sessions, agent_seed):
    from app.features.interview.agent_context import AgentStateError
    from app.features.interview.director_service import process_answer

    await seed_turns(agent_sessions, agent_seed)
    request = c.VerificationRequest(
        "팀원 담당입니다",
        "구현 확인",
        str(agent_seed["repo_id"]),
        agent_seed["sha"],
        ("src/main.py",),
    )
    original = replace(analysis(), needs_verification=True, verification_requests=(request,))
    entered = asyncio.Event()

    async def handle(req):
        if req.url.host == "api.github.com":
            entered.set()
            await asyncio.Event().wait()
        return response(asdict(original))

    options = dict(
        user_id=agent_seed["owner"],
        interview_id=agent_seed["interview_id"],
        turn_no=1,
        text="팀원 담당입니다",
        call_id=uuid4(),
        settings=settings(),
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        task = asyncio.create_task(process_answer(agent_sessions, **options, http_client=http))
        try:
            await asyncio.wait_for(entered.wait(), 5)
            with pytest.raises(AgentStateError, match="call_in_progress"):
                await process_answer(agent_sessions, **options, http_client=http)
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task


@pytest.mark.parametrize("duplicate_claim", [False, True])
async def test_real_lookup_stores_source_before_notification_and_links_evaluation_conflict(
    agent_sessions,
    agent_seed,
    duplicate_claim,
):
    from app.features.interview.director_service import process_answer

    await seed_turns(agent_sessions, agent_seed)
    request = c.VerificationRequest(
        "팀원 담당입니다",
        "구현 확인",
        str(agent_seed["repo_id"]),
        agent_seed["sha"],
        ("src/main.py",),
    )
    original = replace(analysis(), needs_verification=True, verification_requests=(request,))
    root, source, blob = "b" * 40, "c" * 40, "ce013625030ba8dba906f756967f9e9ca394464a"
    prefix = "/repos/owner/sample"
    replies = {
        prefix: {"id": 123, "full_name": "owner/sample", "private": False, "visibility": "public"},
        prefix + "/git/commits/" + agent_seed["sha"]: {
            "sha": agent_seed["sha"],
            "tree": {"sha": root},
        },
        prefix + "/git/trees/" + root: {
            "sha": root,
            "truncated": False,
            "tree": [{"path": "src", "mode": "040000", "type": "tree", "sha": source}],
        },
        prefix + "/git/trees/" + source: {
            "sha": source,
            "truncated": False,
            "tree": [{"path": "main.py", "mode": "100644", "type": "blob", "sha": blob}],
        },
        prefix + "/contents/src/main.py": {
            "type": "file",
            "encoding": "base64",
            "size": 6,
            "path": "src/main.py",
            "sha": blob,
            "content": "aGVsbG8K\n",
        },
    }
    notified = []

    async def notify(items):
        async with agent_sessions() as db:
            for item in items:
                stored = await db.get(Evidence, item.evidence_id)
                assert stored is not None and stored.snippet == "hello\n"
        notified.extend(items)

    async def handle(req):
        if req.url.host == "api.github.com":
            async with agent_sessions.begin() as db:
                await db.execute(select(InterviewSession).with_for_update(nowait=True))
            return httpx.Response(200, json=replies[req.url.path])
        payload = json.loads(json.loads(req.content)["input"][0]["content"][0]["text"])
        if "answer" in payload:
            if not payload["tool_results"]:
                return response(asdict(original))
            assert notified
            item = payload["tool_results"][0]["items"][0]
            checked = replace(
                analysis(),
                claim_checks=(
                    c.ClaimCheck(
                        "팀원 담당입니다",
                        "conflicting",
                        (item["evidence_id"],),
                        ("버전과 조건 추가 확인",),
                    ),
                ),
            )
            if duplicate_claim:
                checked = replace(checked, claim_checks=checked.claim_checks * 2)
            return response(asdict(checked))
        return response(plan("tech_lead") if payload["operation"] == "plan" else approved_review())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        result = await process_answer(
            agent_sessions,
            user_id=agent_seed["owner"],
            interview_id=agent_seed["interview_id"],
            turn_no=1,
            text="팀원 담당입니다",
            call_id=uuid4(),
            settings=settings(),
            http_client=http,
            on_evidence_check=notify,
        )
    assert result.failure is None and result.next_turn_id is not None
    async with agent_sessions() as db:
        link = (await db.scalars(select(TurnEvidence))).one()
        conflict = (await db.scalars(select(EvidenceConflict))).one()
        assert link.usage == "evaluation_basis" and link.turn_id == result.turn_id
        assert conflict.evidence_id == link.evidence_id and conflict.verdict == "unresolved"
        assert conflict.evidence_text == "hello\n" and conflict.claim_id is None
        assert (await db.get(Evidence, link.evidence_id)).retrieved_for_turn == 1
        turn = await db.get(InterviewTurn, result.turn_id)
        assert turn.analysis == json.loads(json.dumps(asdict(original)))
        assert "found" in turn.decision["reason_summary"]
        from app.features.interview.answer_context import load_answer_context, prior_analyses

        next_context = await load_answer_context(
            db,
            user_id=agent_seed["owner"],
            interview_id=agent_seed["interview_id"],
            turn_no=2,
            limits=c.ContextLimits(2, 0, "test"),
        )
        past = await prior_analyses(db, next_context.context)
        assert past[str(result.turn_id)].data.claim_checks[0].status == "conflicting"


@pytest.mark.parametrize("turn_no", [1, 9])
async def test_enrichment_cannot_reset_exhausted_analysis_budget_or_finish(
    agent_sessions,
    agent_seed,
    turn_no,
):
    from app.features.interview.director_service import process_answer

    await seed_turns(agent_sessions, agent_seed, turn_no)
    request = c.VerificationRequest(
        "팀원 담당입니다",
        "구현 확인",
        str(agent_seed["repo_id"]),
        agent_seed["sha"],
        ("src/main.py",),
    )
    original = replace(analysis(), needs_verification=True, verification_requests=(request,))
    sent = []

    async def handle(req):
        if req.url.host == "api.github.com":
            return httpx.Response(500)
        sent.append(req)
        return response({"invalid": True} if len(sent) == 1 else asdict(original))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        result = await process_answer(
            agent_sessions,
            user_id=agent_seed["owner"],
            interview_id=agent_seed["interview_id"],
            turn_no=turn_no,
            text="팀원 담당입니다",
            call_id=uuid4(),
            settings=settings(),
            http_client=http,
        )
    assert result.failure is not None and result.failure.stage == "budget"
    assert result.next_turn_id is None and not result.completed
    assert len(sent) == 2
    async with agent_sessions() as db:
        turn = await db.get(InterviewTurn, result.turn_id)
        assert turn.analysis == json.loads(json.dumps(asdict(original)))
        assert "tool_error" in turn.decision["reason_summary"]
        assert (await db.get(InterviewSession, agent_seed["interview_id"])).status == "in_progress"


async def test_answer_replay_preserves_independent_review_failure(agent_sessions, agent_seed):
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
        return response({**approved_review(), "plan_valid": False})

    options = dict(
        user_id=agent_seed["owner"],
        interview_id=agent_seed["interview_id"],
        turn_no=1,
        text="팀원 담당입니다",
        call_id=uuid4(),
        settings=settings(),
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        first = await process_answer(agent_sessions, **options, http_client=http)
        replay = await process_answer(agent_sessions, **options, http_client=http)
    assert first.failure is not None and first.failure.stage == "semantic"
    assert replay.failure == first.failure and replay.next_turn_id is None
    assert len(sent) == 3 and not replay.accepted


def test_restored_question_does_not_register_its_own_unknown_evidence():
    from app.features.interview.agent_context import AgentStateError
    from app.features.interview.answer_context import restored_question

    context = c.Context(
        "interview",
        None,
        1,
        9,
        (),
        ("hr_manager",),
        (),
        (),
        (),
        None,
        (),
        (),
        c.ContextLimits(2, 0, "test"),
    )
    stored = replace(contract(), basis_refs=(c.BasisRef("evidence", "missing"),))
    turn = InterviewTurn(
        id=uuid4(),
        interview_session_id=uuid4(),
        turn_no=1,
        persona="hr_manager",
        question_text="역할을 설명해 주세요.",
        topic_code="role",
        question_contract=json.loads(json.dumps(asdict(stored))),
        jd_requirement_ids=[],
    )
    with pytest.raises(AgentStateError, match="question_contract_invalid"):
        restored_question(turn, context)


async def test_answer_loader_preserves_authorized_posting_basis_text(agent_sessions, agent_seed):
    from app.features.interview.answer_context import load_answer_context

    await seed_turns(agent_sessions, agent_seed)
    stored = replace(
        contract(), basis_refs=(c.BasisRef("job_posting", str(agent_seed["posting_id"])),)
    )
    async with agent_sessions.begin() as db:
        turn = await db.scalar(select(InterviewTurn))
        turn.question_contract = json.loads(json.dumps(asdict(stored)))
        posting = await db.get(JobPosting, agent_seed["posting_id"])
        posting.raw_payload = {"body": "실제 공고 원문"}
    async with agent_sessions() as db:
        loaded = await load_answer_context(
            db,
            user_id=agent_seed["owner"],
            interview_id=agent_seed["interview_id"],
            turn_no=1,
            limits=c.ContextLimits(2, 0, "test"),
        )
    assert loaded.question.data.question_contract == stored


async def test_director_updates_context_snapshot_without_losing_prepare_state(
    agent_sessions, agent_seed
):
    from app.features.interview.director_service import start_director

    await seed_turns(agent_sessions, agent_seed, 0)
    async with agent_sessions.begin() as db:
        interview = await db.get(InterviewSession, agent_seed["interview_id"])
        interview.context_state = {
            "prepare_job_id": "preserved",
            "preparation_limitations": ["한정 범위"],
        }

    async def handle(req):
        payload = json.loads(json.loads(req.content)["input"][0]["content"][0]["text"])
        return response(plan() if payload["operation"] == "plan" else approved_review())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        result = await start_director(
            agent_sessions,
            user_id=agent_seed["owner"],
            interview_id=agent_seed["interview_id"],
            call_id=uuid4(),
            settings=settings(),
            http_client=http,
        )
    async with agent_sessions() as db:
        interview = await db.get(InterviewSession, agent_seed["interview_id"])
        snapshot = interview.context_state
        assert snapshot["prepare_job_id"] == "preserved"
        assert snapshot["preparation_limitations"] == ["한정 범위"]
        assert snapshot["director"]["current_turn_id"] == str(result.turn_id)
        assert snapshot["director"]["turn_no"] == 1
        assert snapshot["director"]["phase"] == "awaiting_answer"
        assert snapshot["director"]["decision"]["next_step"] == "ask"
