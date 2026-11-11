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
