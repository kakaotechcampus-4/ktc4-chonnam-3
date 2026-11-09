

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
