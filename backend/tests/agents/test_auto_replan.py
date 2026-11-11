"""v12 자동 재계획은 최초 입력과 안전한 원시 검토가 같은 슬롯 안에서만 허용된다."""

import asyncio
import json
from copy import deepcopy
from dataclasses import asdict
from uuid import uuid4, uuid5

import httpx
import pytest
from sqlalchemy import select

from app.core.errors import AppError
from app.db.models import (
    InterviewSession,
    InterviewTurn,
    JobPosting,
    LLMCallRecord,
    PromptVersion,
    User,
)
from app.features.interview.agent_context import AgentStateError
from app.features.interview.director_service import process_answer
from tests.agents.director_helpers import (
    analysis,
    approved_review,
    plan,
    response,
    seed_turns,
    settings,
)
from tests.agents.test_question_retry import Redis, retry


async def seed(sessions, values, version="director_v12", count=1):
    await seed_turns(sessions, values, count)
    async with sessions.begin() as db:
        prompt = await db.scalar(select(PromptVersion).where(PromptVersion.task_name == "director"))
        prompt.version = version
        if count > 1:
            first = await db.scalar(select(InterviewTurn).where(InterviewTurn.turn_no == 1))
            first.analysis = asdict(analysis())


def payload(request):
    return json.loads(json.loads(request.content)["input"][0]["content"][0]["text"])


async def answer(sessions, values, http, *, call_id=None, turn=1):
    return await process_answer(
        sessions,
        user_id=values["owner"],
        interview_id=values["interview_id"],
        turn_no=turn,
        text="팀원 담당입니다",
        call_id=call_id or uuid4(),
        settings=settings(),
        http_client=http,
    )


@pytest.mark.parametrize("version", ["director_v10", "director_v11", "director_v12"])
@pytest.mark.parametrize("kind", ["rewrite", "replan", "no_valid_candidate"])
async def test_versioned_recovery_uses_one_existing_auto_slot_and_preserves_failure(
    agent_sessions, agent_seed, version, kind
):
    await seed(agent_sessions, agent_seed, version)
    sent, reviews, call_id = [], 0, uuid4()

    async def handle(request):
        nonlocal reviews
        item = payload(request)
        sent.append(item)
        if "answer" in item:
            return response(asdict(analysis()))
        if item["operation"] == "plan":
            # 최초 모델 I/O 전에 지문이 확정되어 있어야 한다.
            async with agent_sessions() as db:
                row = await db.get(InterviewSession, agent_seed["interview_id"])
                bindings = row.context_state.get("director_generation_bindings_v1", {})
                assert bool(bindings) is (version == "director_v12")
            return response(plan("tech_lead"))
        reviews += 1
        review = approved_review()
        if reviews == 1:
            review["wording_valid" if kind == "rewrite" else "plan_valid"] = False
            review["safe_alternative"] = kind != "no_valid_candidate"
        return response(review)

    expected_auto = kind == "rewrite" or (kind == "replan" and version == "director_v12")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        result = await answer(agent_sessions, agent_seed, http, call_id=call_id)
        replay = await answer(agent_sessions, agent_seed, http, call_id=call_id)
    assert result.next_turn_id == replay.next_turn_id
    assert (result.failure is None) is expected_auto
    assert len(sent) == (5 if expected_auto else 3)
    assert sum("answer" in item for item in sent) == 1
    async with agent_sessions() as db:
        original = await db.get(LLMCallRecord, uuid5(call_id, "director"))
        assert original.failure["error_code"] == "director_" + (
            "no_valid_candidate" if kind == "no_valid_candidate" else "candidate_" + kind
        )
        assert original.turn_id is None and len(original.attempts) == 2
        row = await db.get(InterviewSession, agent_seed["interview_id"])
        ledger = row.context_state.get("question_retry_v1", {})
        assert len(ledger) == int(expected_auto)
        if expected_auto:
            entry = next(iter(ledger.values()))
            assert entry["kind"] == "auto" and entry["recovery_kind"] == kind
            assert entry["request_id"] == str(uuid5(original.id, "automatic-rewrite"))
            assert entry["status"] == "succeeded"
        if version == "director_v12":
            assert len(row.context_state["director_generation_bindings_v1"]) == 1 + int(
                expected_auto
            )


@pytest.mark.parametrize("version", ["director_v14@candidate", "director_v16@candidate"])
async def test_point_review_rewrites_an_unasked_requirement_and_stores_only_the_reviewed_question(
    agent_sessions, agent_seed, version
):
    await seed(agent_sessions, agent_seed, version)
    async with agent_sessions.begin() as db:
        prompt = await db.scalar(select(PromptVersion).where(PromptVersion.task_name == "director"))
        prompt.template = "## 공통\n근거 규칙\n## 질문 생성\n생성 지침\n## 독립 검토\n검토 지침\n"
    sent, plans, reviews, call_id = [], 0, 0, uuid4()

    async def handle(request):
        nonlocal plans, reviews
        item = payload(request)
        sent.append(item)
        if "answer" in item:
            return response(asdict(analysis()))
        if item["operation"] == "plan":
            plans += 1
            candidate = plan("tech_lead")
            if plans == 1:
                candidate["question"]["question_contract"]["required_points"][0]["description"] += (
                    "와 장애 복구 절차"
                )
            return response(candidate)
        reviews += 1
        (point,) = item["question"]["question_contract"]["required_points"]
        receipt = {
            "status": "not_asked" if reviews == 1 else "asked",
            "question_excerpt": None if reviews == 1 else "본인의 역할을 설명",
        }
        return response(
            {
                **approved_review(),
                "point_coverage": (
                    [{"key": point["key"], **receipt}]
                    if version == "director_v16@candidate"
                    else {point["key"]: receipt}
                ),
            }
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        result = await answer(agent_sessions, agent_seed, http, call_id=call_id)
        replay = await answer(agent_sessions, agent_seed, http, call_id=call_id)
    assert result.failure is None and result.next_turn_id == replay.next_turn_id
    assert len(sent) == 5 and plans == reviews == 2
    assert sent[3]["recovery_feedback"]["recovery"] == "rewrite"
    assert "recovery_feedback" not in sent[4]
    async with agent_sessions() as db:
        original = await db.get(LLMCallRecord, uuid5(call_id, "director"))
        assert original.failure["error_code"] == "director_candidate_rewrite"
        assert original.attempts[1]["schema_version"] == (
            "director-review.v3" if version == "director_v16@candidate" else "director-review.v2"
        )
        assert isinstance(original.attempts[1]["raw_output"], str)
        assert original.turn_id is None
        stored = await db.get(InterviewTurn, result.next_turn_id)
        assert "장애 복구 절차" not in json.dumps(stored.question_contract, ensure_ascii=False)
        assert len(list(await db.scalars(select(InterviewTurn)))) == 2


@pytest.mark.parametrize(
    "change",
    ["missing", "digest", "source", "past", "analysis", "template", "model", "version", "owner"],
)
@pytest.mark.parametrize("kind", ["rewrite", "replan"])
async def test_first_generation_identity_change_blocks_automatic_and_manual_recovery(
    agent_sessions, agent_seed, change, kind
):
    await seed(agent_sessions, agent_seed, count=2)
    sent = []

    async def handle(request):
        item = payload(request)
        sent.append(item)
        if "answer" in item:
            return response(asdict(analysis()))
        if item["operation"] == "plan":
            return response(plan("tech_lead"))
        async with agent_sessions.begin() as db:
            row = await db.get(InterviewSession, agent_seed["interview_id"])
            if change in {"missing", "digest"}:
                state = deepcopy(row.context_state)
                if change == "missing":
                    state.pop("director_generation_bindings_v1", None)
                else:
                    for binding in state.get("director_generation_bindings_v1", {}).values():
                        binding["binding"] = "0" * 64
                row.context_state = state
            elif change == "source":
                (await db.get(JobPosting, row.job_posting_id)).raw_payload = {"changed": "source"}
            elif change in {"past", "analysis"}:
                turn = await db.scalar(
                    select(InterviewTurn).where(
                        InterviewTurn.turn_no == (1 if change == "past" else 2)
                    )
                )
                changed = deepcopy(turn.analysis)
                changed["limitations"].append("추가 미확인 범위")
                turn.analysis = changed
                if change == "analysis":
                    # 현재 분석은 prior_analyses가 성공한 마지막 T3 원시 출력으로 복원한다.
                    # JSONB만 바꾸면 실제 typed 입력은 그대로이므로 그 원시 기록도 바꾼다.
                    record = await db.scalar(
                        select(LLMCallRecord).where(
                            LLMCallRecord.task_name == "answer_analysis",
                            LLMCallRecord.turn_id == turn.id,
                        )
                    )
                    attempts = deepcopy(record.attempts)
                    attempts[-1]["raw_output"] = json.dumps(changed, ensure_ascii=False)
                    record.attempts = attempts
            elif change == "owner":
                (await db.get(User, agent_seed["owner"])).status = "suspended"
            else:
                prompt = await db.scalar(
                    select(PromptVersion).where(PromptVersion.task_name == "director")
                )
                setattr(prompt, change, "director_v10" if change == "version" else "changed-value")
        return response(
            {**approved_review(), "wording_valid" if kind == "rewrite" else "plan_valid": False}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        if change == "owner":
            with pytest.raises(AgentStateError):
                await answer(agent_sessions, agent_seed, http, turn=2)
        else:
            result = await answer(agent_sessions, agent_seed, http, turn=2)
            assert result.failure is not None and result.next_turn_id is None
        assert len(sent) == 3
        with pytest.raises(AppError):
            await retry(agent_sessions, agent_seed, Redis(), uuid4(), http)
        assert len(sent) == 3
    async with agent_sessions() as db:
        assert len(list(await db.scalars(select(InterviewTurn)))) == 2


@pytest.mark.parametrize("kind", ["rewrite", "replan"])
async def test_active_v12_cannot_promote_a_legacy_failure(agent_sessions, agent_seed, kind):
    await seed(agent_sessions, agent_seed, "director_v10")
    sent = []

    async def handle(request):
        item = payload(request)
        sent.append(item)
        if "answer" in item:
            return response(asdict(analysis()))
        if item["operation"] == "plan":
            return response(plan("tech_lead"))
        async with agent_sessions.begin() as db:
            prompt = await db.scalar(
                select(PromptVersion).where(PromptVersion.task_name == "director")
            )
            prompt.version = "director_v12"
        return response(
            {**approved_review(), "wording_valid" if kind == "rewrite" else "plan_valid": False}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        result = await answer(agent_sessions, agent_seed, http)
    assert result.next_turn_id is None and result.failure is not None and len(sent) == 3


async def test_replan_and_rewrite_share_the_same_auto_slot_and_six_director_call_ceiling(
    agent_sessions, agent_seed
):
    await seed(agent_sessions, agent_seed)
    sent, reviews = [], 0

    async def handle(request):
        nonlocal reviews
        item = payload(request)
        sent.append(item)
        if "answer" in item:
            return response(asdict(analysis()))
        if item["operation"] == "plan":
            return response(plan("tech_lead"))
        reviews += 1
        return response(
            {**approved_review(), "wording_valid" if reviews == 2 else "plan_valid": False}
        )

    rid, redis = uuid4(), Redis()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        result = await answer(agent_sessions, agent_seed, http)
        assert result.failure is not None and len(sent) == 5
        for request_id in [rid, rid, uuid4()]:
            with pytest.raises(AppError):
                await retry(agent_sessions, agent_seed, redis, request_id, http)
        assert len(sent) == 7
    async with agent_sessions() as db:
        row = await db.get(InterviewSession, agent_seed["interview_id"])
        ledger = row.context_state["question_retry_v1"]
        assert len(ledger) == 2 and sum(item["kind"] == "auto" for item in ledger.values()) == 1
        assert len(row.context_state["director_generation_bindings_v1"]) == 3


async def test_unshielded_auto_replan_cancellation_terminalizes_owned_slot(
    agent_sessions, agent_seed
):
    await seed(agent_sessions, agent_seed)
    entered, hold = asyncio.Event(), asyncio.Event()
    sent, reviews, call_id = [], 0, uuid4()

    async def handle(request):
        nonlocal reviews
        item = payload(request)
        sent.append(item)
        if "answer" in item:
            return response(asdict(analysis()))
        if item["operation"] == "plan":
            if reviews:
                entered.set()
                await hold.wait()
            return response(plan("tech_lead"))
        reviews += 1
        return response({**approved_review(), "plan_valid": False})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        caller = asyncio.create_task(answer(agent_sessions, agent_seed, http, call_id=call_id))
        try:
            await asyncio.wait_for(entered.wait(), 10)
            caller.cancel()
            with pytest.raises(asyncio.CancelledError):
                await caller
        finally:
            hold.set()
            if not caller.done():
                caller.cancel()
                await asyncio.gather(caller, return_exceptions=True)
        before = len(sent)
        await answer(agent_sessions, agent_seed, http, call_id=call_id)
        assert len(sent) == before == 4
    async with agent_sessions() as db:
        row = await db.get(InterviewSession, agent_seed["interview_id"])
        ledger = row.context_state["question_retry_v1"]
        assert len(ledger) == 1 and next(iter(ledger.values()))["status"] == "failed"
        turn = await db.scalar(select(InterviewTurn))
        assert turn.status == "answered" and turn.answer_text == "팀원 담당입니다"


async def test_cancelled_manual_replan_child_success_replays_one_session_without_model_calls(
    agent_sessions, agent_seed
):
    from app.features.interview import question_retry

    await seed(agent_sessions, agent_seed)
    entered, release = asyncio.Event(), asyncio.Event()
    sent, reviews, call_id = [], 0, uuid4()

    async def handle(request):
        nonlocal reviews
        item = payload(request)
        sent.append(item)
        if "answer" in item:
            return response(asdict(analysis()))
        if item["operation"] == "plan":
            if reviews == 2:
                entered.set()
                await release.wait()
            return response(plan("tech_lead"))
        reviews += 1
        return response(
            {**approved_review(), "plan_valid": False, "safe_alternative": reviews != 1}
            if reviews < 3
            else approved_review()
        )

    redis, rid = Redis(), uuid4()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        failed = await answer(agent_sessions, agent_seed, http, call_id=call_id)
        assert failed.failure.error_code == "director_no_valid_candidate" and len(sent) == 3
        caller = asyncio.create_task(retry(agent_sessions, agent_seed, redis, rid, http))
        try:
            await asyncio.wait_for(entered.wait(), 10)
            caller.cancel()
            with pytest.raises(asyncio.CancelledError):
                await caller
            with pytest.raises(AppError) as pending:
                await retry(agent_sessions, agent_seed, redis, rid, http)
            assert pending.value.reason.value == "question_retry_in_progress"
        finally:
            release.set()
            if not caller.done():
                caller.cancel()
                await asyncio.gather(caller, return_exceptions=True)
        await asyncio.wait_for(asyncio.gather(*tuple(question_retry._RUNNING)), 10)
        first = await retry(agent_sessions, agent_seed, redis, rid, http)
        again = await retry(agent_sessions, agent_seed, redis, rid, http)
        replay = await answer(agent_sessions, agent_seed, http, call_id=call_id)
    assert first == again and replay.next_turn_id is not None
    assert len(sent) == 7 and len(redis.calls) == 2
    async with agent_sessions() as db:
        row = await db.get(InterviewSession, agent_seed["interview_id"])
        ledger = row.context_state["question_retry_v1"]
        manual = ledger[str(rid)]
        child = ledger[
            str(
                uuid5(
                    uuid5(agent_seed["interview_id"], "director-question-retry:" + str(rid)),
                    "automatic-rewrite",
                )
            )
        ]
        assert child["recovery_kind"] == "replan" and child["binding"] == manual["binding"]
        assert child["status"] == manual["status"] == "succeeded"
        assert question_retry.progress(row).request_id == rid


@pytest.mark.parametrize("change", ["past", "deadline", "owner"])
async def test_auto_replan_commit_rechecks_past_analysis_deadline_and_owner(
    agent_sessions, agent_seed, change
):
    from datetime import UTC, datetime, timedelta

    await seed(agent_sessions, agent_seed, count=2)
    sent, reviews = [], 0

    async def handle(request):
        nonlocal reviews
        item = payload(request)
        sent.append(item)
        if "answer" in item:
            return response(asdict(analysis()))
        if item["operation"] == "plan":
            if reviews:
                async with agent_sessions.begin() as db:
                    row = await db.get(InterviewSession, agent_seed["interview_id"])
                    if change == "past":
                        first = await db.scalar(
                            select(InterviewTurn).where(InterviewTurn.turn_no == 1)
                        )
                        changed = deepcopy(first.analysis)
                        changed["limitations"].append("결과 확정 전 수정")
                        first.analysis = changed
                    else:
                        state = deepcopy(row.context_state)
                        entry = next(iter(state["question_retry_v1"].values()))
                        if change == "deadline":
                            entry["deadline"] = (
                                datetime.now(UTC) - timedelta(seconds=1)
                            ).isoformat()
                        else:
                            entry["owner"] = str(uuid4())
                        row.context_state = state
            return response(plan("tech_lead"))
        reviews += 1
        return response({**approved_review(), "plan_valid": reviews > 1})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        result = await answer(agent_sessions, agent_seed, http, turn=2)
    assert result.next_turn_id is None and len(sent) == 5
    async with agent_sessions() as db:
        assert len(list(await db.scalars(select(InterviewTurn)))) == 2
        row = await db.get(InterviewSession, agent_seed["interview_id"])
        entry = next(iter(row.context_state["question_retry_v1"].values()))
        assert entry["status"] != "succeeded"


@pytest.mark.parametrize("corruption", ["missing_raw", "unsafe", "classification", "version"])
async def test_auto_replan_requires_exact_consistent_raw_feedback(
    agent_sessions, agent_seed, monkeypatch, corruption
):
    from app.features.interview import question_retry

    await seed(agent_sessions, agent_seed)
    original_auto = question_retry.auto_retry_question
    sent = []

    async def corrupt_then_check(sessions, **kwargs):
        async with sessions.begin() as db:
            record = await db.get(LLMCallRecord, kwargs["failed"].call_id)
            changed = deepcopy(record.attempts)
            if corruption == "missing_raw":
                changed[0]["raw_output"] = None
            elif corruption == "version":
                changed[1]["prompt_version"] = "director_v10"
            else:
                review = json.loads(changed[1]["raw_output"])
                review["safe_alternative" if corruption == "unsafe" else "plan_valid"] = (
                    False if corruption == "unsafe" else True
                )
                changed[1]["raw_output"] = json.dumps(review, ensure_ascii=False)
            record.attempts = changed
        return await original_auto(sessions, **kwargs)

    monkeypatch.setattr(question_retry, "auto_retry_question", corrupt_then_check)

    async def handle(request):
        item = payload(request)
        sent.append(item)
        if "answer" in item:
            return response(asdict(analysis()))
        return response(
            plan("tech_lead")
            if item["operation"] == "plan"
            else {**approved_review(), "plan_valid": False}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        result = await answer(agent_sessions, agent_seed, http)
    assert result.next_turn_id is None and result.failure is not None and len(sent) == 3
