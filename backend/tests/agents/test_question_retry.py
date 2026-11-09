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


async def test_expired_reservation_is_terminal_without_provider_calls(agent_sessions, agent_seed):
    from datetime import UTC, datetime, timedelta

    from app.features.interview.question_retry import _reserve

    await failed_question(agent_sessions, agent_seed)
    request_id = uuid4()
    await _reserve(
        agent_sessions,
        user_id=agent_seed["owner"],
        interview_id=agent_seed["interview_id"],
        request_id=request_id,
        kind="manual",
        settings=settings(),
    )
    async with agent_sessions.begin() as db:
        row = await db.get(InterviewSession, agent_seed["interview_id"])
        state = deepcopy(row.context_state)
        state["question_retry_v1"][str(request_id)]["deadline"] = (
            datetime.now(UTC) - timedelta(seconds=1)
        ).isoformat()
        row.context_state = state

    async def forbidden(req):
        pytest.fail("expired reservation called the model")

    async with httpx.AsyncClient(transport=httpx.MockTransport(forbidden)) as http:
        for rid, expected in [
            (request_id, "question_retry_failed"),
            (uuid4(), "question_retry_limit"),
        ]:
            with pytest.raises(AppError) as error:
                await retry(agent_sessions, agent_seed, Redis(), rid, http)
            assert error.value.reason.value == expected


@pytest.mark.parametrize("cause", ["timeout", "context_changed"])
async def test_running_retry_failure_returns_the_documented_error_and_is_not_reexecuted(
    agent_sessions, agent_seed, monkeypatch, cause
):
    from app.features.interview import director_service
    from app.features.interview.agent_context import AgentStateError

    turn_id, _ = await failed_question(agent_sessions, agent_seed)
    calls = []

    async def fail(*args, **kwargs):
        calls.append(kwargs["call_id"])
        if cause == "timeout":
            raise TimeoutError
        raise AgentStateError("context_changed")

    monkeypatch.setattr(director_service, "start_director", fail)
    request_id = uuid4()
    for _ in range(2):
        with pytest.raises(AppError) as error:
            await retry(agent_sessions, agent_seed, Redis(), request_id, None)
        assert error.value.reason.value == "question_retry_failed"
    assert len(calls) == 1
    async with agent_sessions() as db:
        row = await db.get(InterviewSession, agent_seed["interview_id"])
        assert row.context_state["question_retry_v1"][str(request_id)]["status"] == "failed"
        turn = await db.get(InterviewTurn, turn_id)
        assert turn.answer_text == "팀원 담당입니다" and turn.analysis is not None


@pytest.mark.parametrize("status,allowed", [(503, True), (401, False)])
async def test_provider_failure_policy_survives_real_storage_and_changed_description(
    agent_sessions, agent_seed, status, allowed
):
    from dataclasses import replace

    from pydantic import SecretStr

    from app.features.interview.question_retry import availability
    from app.integrations.llm.client import call_model
    from tests.integrations.test_llm_client import request, validate

    _, failed_id = await failed_question(agent_sessions, agent_seed)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda req: httpx.Response(status, headers={"Retry-After": "0"})
        )
    ) as http:
        result = await call_model(
            replace(request(), max_attempts=1),
            validate,
            api_key=SecretStr("fixture"),
            base_url="https://provider.invalid/v1",
            http_client=http,
        )
    async with agent_sessions.begin() as db:
        row = await db.get(LLMCallRecord, failed_id)
        row.failure = {**asdict(result.failure), "reason_summary": "설명 문구가 변경됐습니다."}
        row.attempts = [asdict(item) for item in result.attempts]
    async with agent_sessions() as db:
        stored = await db.get(LLMCallRecord, failed_id)
        assert stored.failure["provider_status"] == status
        interview = await db.get(InterviewSession, agent_seed["interview_id"])
        # 두 번째 값은 남은 횟수가 아닌 이미 사용한 수동 재생성 횟수다.
        assert await availability(db, interview) == ((True, 0) if allowed else (False, 0))


async def test_availability_excludes_t3_failure_and_reports_manual_limit(
    agent_sessions, agent_seed
):
    from app.features.interview.question_retry import _reserve, availability

    await failed_question(agent_sessions, agent_seed)
    async with agent_sessions() as db:
        row = await db.get(InterviewSession, agent_seed["interview_id"])
        assert await availability(db, row) == (True, 0)
    await _reserve(
        agent_sessions,
        user_id=agent_seed["owner"],
        interview_id=agent_seed["interview_id"],
        request_id=uuid4(),
        kind="manual",
        settings=settings(),
    )
    async with agent_sessions() as db:
        row = await db.get(InterviewSession, agent_seed["interview_id"])
        assert await availability(db, row) == (False, 1)


async def test_manual_retry_after_four_answers_keeps_all_original_rows(agent_sessions, agent_seed):
    from app.db.models import RepoAnalysis

    turn_id, failed_id = await failed_question(agent_sessions, agent_seed)
    async with agent_sessions.begin() as db:
        row = await db.get(InterviewSession, agent_seed["interview_id"])
        row.current_turn = 4
        first = await db.get(InterviewTurn, turn_id)
        for number in range(2, 5):
            db.add(
                InterviewTurn(
                    interview_session_id=row.id,
                    turn_no=number,
                    persona="tech_lead",
                    question_text=first.question_text,
                    question_contract=first.question_contract,
                    topic_code="role",
                    status="answered",
                    answer_text=first.answer_text,
                    analysis=first.analysis,
                )
            )
        await db.flush()
        fourth = await db.scalar(
            select(InterviewTurn).where(
                InterviewTurn.interview_session_id == row.id, InterviewTurn.turn_no == 4
            )
        )
        db.add(
            LLMCallRecord(
                interview_session_id=row.id,
                turn_id=fourth.id,
                turn_no=4,
                task_name="answer_analysis",
                attempts=[{"error_stage": None}],
            )
        )
        (await db.get(LLMCallRecord, failed_id)).turn_no = 5
    async with agent_sessions() as db:
        before = [
            (turn.id, turn.question_text, turn.answer_text, turn.analysis)
            for turn in await db.scalars(select(InterviewTurn).order_by(InterviewTurn.turn_no))
        ]
        analyses = [
            (item.id, item.head_sha, item.result) for item in await db.scalars(select(RepoAnalysis))
        ]
    calls = []

    async def handler(req):
        calls.append(req)
        return response(plan("tech_lead") if len(calls) == 1 else approved_review())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        result = await retry(agent_sessions, agent_seed, Redis(), uuid4(), http)
    assert result.turn_no == 5 and len(calls) == 2
    async with agent_sessions() as db:
        after = [
            (turn.id, turn.question_text, turn.answer_text, turn.analysis)
            for turn in await db.scalars(
                select(InterviewTurn)
                .where(InterviewTurn.turn_no <= 4)
                .order_by(InterviewTurn.turn_no)
            )
        ]
        assert before == after
        assert analyses == [
            (item.id, item.head_sha, item.result) for item in await db.scalars(select(RepoAnalysis))
        ]


async def v7(sessions):
    from app.db.models import PromptVersion

    async with sessions.begin() as db:
        prompt = await db.scalar(select(PromptVersion).where(PromptVersion.task_name == "director"))
        prompt.version = "director_v7"


@pytest.mark.parametrize("accept_auto", [True, False])
async def test_initial_auto_then_manual_never_exceeds_three_director_rounds(
    agent_sessions, agent_seed, accept_auto
):
    import json

    from app.features.interview.director_service import process_answer

    await seed_turns(agent_sessions, agent_seed)
    await v7(agent_sessions)
    requests = []
    reviews = 0

    async def handler(req):
        nonlocal reviews
        payload = json.loads(json.loads(req.content)["input"][0]["content"][0]["text"])
        requests.append(payload)
        if "answer" in payload:
            return response(asdict(analysis()))
        if payload["operation"] == "plan":
            return response(plan("tech_lead"))
        reviews += 1
        return response({**approved_review(), "wording_valid": accept_auto and reviews == 2})

    request_id = uuid4()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        first = await process_answer(
            agent_sessions,
            user_id=agent_seed["owner"],
            interview_id=agent_seed["interview_id"],
            turn_no=1,
            text="팀원 담당입니다",
            call_id=uuid4(),
            settings=settings(),
            http_client=http,
        )
        assert len(requests) == 5  # T3 한 번 + 최초 두 번 + 안전 자동 복구 두 번
        if accept_auto:
            assert first.next_turn_id is not None and first.failure is None
        else:
            assert first.next_turn_id is None and first.failure is not None
            for rid, expected in [
                (request_id, "question_retry_failed"),
                (request_id, "question_retry_failed"),
                (uuid4(), "question_retry_limit"),
            ]:
                with pytest.raises(AppError) as error:
                    await retry(agent_sessions, agent_seed, Redis(), rid, http)
                assert error.value.reason.value == expected
            assert len(requests) == 7  # T3를 제외하면 질문 대상 총 여섯 번
    async with agent_sessions() as db:
        original = list(
            await db.scalars(select(LLMCallRecord).where(LLMCallRecord.task_name == "director"))
        )
        assert len(original) == (2 if accept_auto else 3)
        assert sum(len(record.attempts) for record in original) == (4 if accept_auto else 6)


async def test_legacy_failure_manual_then_unused_auto_is_allowed_once(agent_sessions, agent_seed):
    import json

    await failed_question(agent_sessions, agent_seed)
    await v7(agent_sessions)
    requests = []
    reviews = 0

    async def handler(req):
        nonlocal reviews
        payload = json.loads(json.loads(req.content)["input"][0]["content"][0]["text"])
        requests.append(payload)
        if payload["operation"] == "plan":
            return response(plan("tech_lead"))
        reviews += 1
        return response({**approved_review(), "wording_valid": reviews == 2})

    rid, redis = uuid4(), Redis()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        first = await retry(agent_sessions, agent_seed, redis, rid, http)
        again = await retry(agent_sessions, agent_seed, redis, rid, http)
    assert first == again and first.turn_no == 2 and len(requests) == 4
    plans = [item for item in requests if item["operation"] == "plan"]
    assert "recovery_feedback" not in plans[0] and "recovery_feedback" in plans[1]
    assert all(
        "recovery_feedback" not in item for item in requests if item["operation"] == "review"
    )


async def test_cancelled_manual_auto_child_success_replays_without_any_new_generation(
    agent_sessions, agent_seed
):
    import json

    from app.features.interview import question_retry

    await failed_question(agent_sessions, agent_seed)
    await v7(agent_sessions)
    entered, release = asyncio.Event(), asyncio.Event()
    calls, plans, reviews = [], 0, 0

    async def handler(req):
        nonlocal plans, reviews
        payload = json.loads(json.loads(req.content)["input"][0]["content"][0]["text"])
        calls.append(payload)
        if payload["operation"] == "plan":
            plans += 1
            if plans == 2:
                entered.set()
                await release.wait()
            return response(plan("tech_lead"))
        reviews += 1
        return response({**approved_review(), "wording_valid": reviews == 2})

    redis, rid = Redis(), uuid4()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        caller = asyncio.create_task(retry(agent_sessions, agent_seed, redis, rid, http))
        await asyncio.wait_for(entered.wait(), 10)
        caller.cancel()
        with pytest.raises(asyncio.CancelledError):
            await caller
        with pytest.raises(AppError) as pending:
            await retry(agent_sessions, agent_seed, redis, rid, http)
        assert pending.value.reason.value == "question_retry_in_progress"
        release.set()
        await asyncio.wait_for(asyncio.gather(*tuple(question_retry._RUNNING)), 10)
        result = await retry(agent_sessions, agent_seed, redis, rid, http)
    assert result.turn_no == 2 and len(calls) == 4 and len(redis.calls) == 1


async def test_original_failure_replay_returns_explicitly_recovered_following_question(
    agent_sessions, agent_seed
):
    from app.features.interview.director_service import process_answer

    turn_id, failure_id = await failed_question(agent_sessions, agent_seed)
    async with agent_sessions() as db:
        original_call = await db.scalar(
            select(LLMCallRecord.id).where(LLMCallRecord.task_name == "answer_analysis")
        )
    request_id, calls = uuid4(), []

    async def handler(req):
        calls.append(req)
        return response(plan("tech_lead") if len(calls) == 1 else approved_review())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        result = await retry(agent_sessions, agent_seed, Redis(), request_id, http)
        replay = await process_answer(
            agent_sessions,
            user_id=agent_seed["owner"],
            interview_id=agent_seed["interview_id"],
            turn_no=1,
            text="팀원 담당입니다",
            call_id=original_call,
            settings=settings(),
            http_client=http,
        )
    assert result.turn_no == 2 and replay.next_turn_id is not None and replay.failure is None
    assert len(calls) == 2
    async with agent_sessions() as db:
        assert (await db.get(InterviewTurn, turn_id)).answer_text == "팀원 담당입니다"
        assert (await db.get(LLMCallRecord, failure_id)).failure[
            "error_code"
        ] == "director_candidate_rewrite"


async def test_real_redis_rotates_closed_session_and_replays_without_model_calls(
    agent_sessions, agent_seed
):
    import json
    import os
    from urllib.parse import urlsplit

    from redis.asyncio import Redis as ActualRedis

    url = os.environ["TEST_REDIS_URL"]
    parsed = urlsplit(url)
    assert parsed.hostname in {"127.0.0.1", "localhost"} and int(parsed.path[1:]) >= 13
    redis = ActualRedis.from_url(url)
    await failed_question(agent_sessions, agent_seed)
    previous_session, request_id, calls = str(uuid4()), uuid4(), []
    reverse = f"rt:interview:{agent_seed['interview_id']}"
    await redis.set(reverse, previous_session)
    await redis.set(f"rt:{previous_session}", "old")

    async def handler(req):
        calls.append(req)
        return response(plan("tech_lead") if len(calls) == 1 else approved_review())

    result = None
    try:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            result = await retry(agent_sessions, agent_seed, redis, request_id, http)
            again = await retry(agent_sessions, agent_seed, redis, request_id, http)
        assert result == again and result.session_id != previous_session
        assert await redis.get(reverse) == result.session_id.encode()
        assert await redis.get(f"rt:{previous_session}") is None
        body = json.loads(await redis.get(f"rt:{result.session_id}"))
        assert body["userId"] == str(agent_seed["owner"])
        assert len(calls) == 2
    finally:
        await redis.delete(reverse, f"rt:{previous_session}")
        if result:
            await redis.delete(f"rt:{result.session_id}")
        await redis.aclose()


@pytest.mark.parametrize("automatic", [False, True])
async def test_concurrent_manual_replay_during_commit_preserves_one_success_session(
    agent_sessions, agent_seed, monkeypatch, automatic
):
    import json

    from app.features.interview import director_service

    await failed_question(agent_sessions, agent_seed)
    await v7(agent_sessions)
    committed, release = asyncio.Event(), asyncio.Event()
    original_start = director_service.start_director

    async def pause_after_automatic_question(*args, **kwargs):
        outcome = await original_start(*args, **kwargs)
        if (
            kwargs.get("recovery_feedback") is not None
        ) == automatic and outcome.turn_id is not None:
            committed.set()
            await release.wait()
        return outcome

    monkeypatch.setattr(director_service, "start_director", pause_after_automatic_question)
    requests, reviews = [], 0

    async def handler(req):
        nonlocal reviews
        payload = json.loads(json.loads(req.content)["input"][0]["content"][0]["text"])
        requests.append(payload)
        if payload["operation"] == "plan":
            return response(plan("tech_lead"))
        reviews += 1
        return response({**approved_review(), "wording_valid": not automatic or reviews == 2})

    redis, request_id = Redis(), uuid4()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        first_caller = asyncio.create_task(
            retry(agent_sessions, agent_seed, redis, request_id, http)
        )
        try:
            await asyncio.wait_for(committed.wait(), 10)
            repeated = await retry(agent_sessions, agent_seed, redis, request_id, http)
        finally:
            release.set()
        first = await first_caller
    assert first == repeated and first.turn_no == 2
    assert len(requests) == (4 if automatic else 2) and len(redis.calls) == 2
    assert redis.calls[0][1] == redis.calls[1][1] == first.session_id
    async with agent_sessions() as db:
        assert len(list(await db.scalars(select(InterviewTurn)))) == 2
        row = await db.get(InterviewSession, agent_seed["interview_id"])
        assert {entry["status"] for entry in row.context_state["question_retry_v1"].values()} == {
            "succeeded"
        }


async def test_permanent_failure_cannot_consume_manual_round(agent_sessions, agent_seed):
    from app.features.interview.question_retry import availability

    _, failed_id = await failed_question(agent_sessions, agent_seed)
    async with agent_sessions.begin() as db:
        failed = await db.get(LLMCallRecord, failed_id)
        failed.failure = {
            "stage": "provider",
            "error_code": "llm_failed",
            "reason_summary": "Provider HTTP 401 request failed.",
        }
    async with agent_sessions() as db:
        row = await db.get(InterviewSession, agent_seed["interview_id"])
        assert await availability(db, row) == (False, 0)

    async def forbidden(req):
        pytest.fail("영구 인증 오류를 수동 라운드로 다시 호출하면 안 된다")

    async with httpx.AsyncClient(transport=httpx.MockTransport(forbidden)) as http:
        with pytest.raises(AppError) as error:
            await retry(agent_sessions, agent_seed, Redis(), uuid4(), http)
    assert error.value.reason.value == "question_retry_unavailable"


async def test_running_request_identity_survives_detail_refresh(agent_sessions, agent_seed):
    from app.features.interview.question_retry import _reserve, progress

    await failed_question(agent_sessions, agent_seed)
    request_id = uuid4()
    await _reserve(
        agent_sessions,
        user_id=agent_seed["owner"],
        interview_id=agent_seed["interview_id"],
        request_id=request_id,
        kind="manual",
        settings=settings(),
    )
    async with agent_sessions() as db:
        row = await db.get(InterviewSession, agent_seed["interview_id"])
        state = progress(row)
        assert state.request_id == request_id
        assert state.status == "running" and state.turn_no == 2


async def test_old_success_never_rotates_after_answer_or_later_turn(agent_sessions, agent_seed):
    await failed_question(agent_sessions, agent_seed)
    sent = []

    async def handler(req):
        sent.append(req)
        return response(plan("tech_lead") if len(sent) == 1 else approved_review())

    request_id, redis = uuid4(), Redis()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        await retry(agent_sessions, agent_seed, redis, request_id, http)
        async with agent_sessions.begin() as db:
            turn = await db.scalar(select(InterviewTurn).where(InterviewTurn.turn_no == 2))
            turn.status, turn.answer_text = "answered", "확정 답변"
        before = len(redis.calls)
        with pytest.raises(AppError) as error:
            await retry(agent_sessions, agent_seed, redis, request_id, http)
        assert error.value.reason.value == "question_retry_unavailable"
        assert len(redis.calls) == before and len(sent) == 2
