

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
