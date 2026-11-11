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
