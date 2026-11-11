async def test_valid_second_t3_attempt_can_continue_after_empty_lookup_without_budget_failure(
    agent_sessions, agent_seed
):
    await seed_version(agent_sessions, agent_seed, "director_v9")
    original, sent = requesting_analysis(agent_seed), []

    async def handle(request):
        if request.url.host == "api.github.com":
            return httpx.Response(500)
        payload = json.loads(json.loads(request.content)["input"][0]["content"][0]["text"])
        sent.append(payload)
        if "answer" in payload:
            return response({"invalid": True} if len(sent) == 1 else asdict(original))
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
        )
    assert result.failure is None and result.next_turn_id is not None
    assert len(sent) == 4
    async with agent_sessions() as db:
        record = await db.get(LLMCallRecord, result.call_id)
        assert len(record.attempts) == 2 and record.failure is None


async def test_reused_analysis_cannot_run_under_a_different_director_prompt(
    agent_sessions, agent_seed
):
    await seed_version(agent_sessions, agent_seed, "director_v8")
    async with agent_sessions.begin() as db:
        turn = await db.scalar(select(InterviewTurn))
        turn.status, turn.answer_text, turn.analysis = (
            "answered",
            "팀원 담당입니다",
            asdict(analysis()),
        )
    expected = c.PromptSpec("director", "director_v9", "db-model", "질문 생성 fixture")

    async def forbidden(request):
        pytest.fail("프롬프트 정책이 달라지면 모델 호출 전에 거절해야 합니다")

    async with httpx.AsyncClient(transport=httpx.MockTransport(forbidden)) as http:
        result = await start_director(
            agent_sessions,
            user_id=agent_seed["owner"],
            interview_id=agent_seed["interview_id"],
            call_id=uuid4(),
            settings=settings(),
            expected_prompt=expected,
            http_client=http,
        )
    assert result.turn_id is None and result.discard_reason == "context_changed"
    async with agent_sessions() as db:
        record = await db.get(LLMCallRecord, result.call_id)
        assert record is not None and record.discard_reason == "context_changed"
        assert record.attempts == []


@pytest.mark.parametrize("mode", ["auto", "manual"])
@pytest.mark.parametrize("change", ["version", "template", "model"])
async def test_empty_lookup_policy_is_preserved_through_question_recovery(
    agent_sessions, agent_seed, mode, change
):
    from app.core.errors import AppError
    from app.features.interview.question_retry import availability
    from tests.agents.test_question_retry import Redis, retry

    await seed_version(agent_sessions, agent_seed, "director_v10")
    original, sent, reviews = requesting_analysis(agent_seed), [], 0

    async def handle(request):
        nonlocal reviews
        if request.url.host == "api.github.com":
            return httpx.Response(500)
        payload = json.loads(json.loads(request.content)["input"][0]["content"][0]["text"])
        sent.append(payload)
        if "answer" in payload:
            return response(asdict(original))
        if payload["operation"] == "plan":
            return response(plan("tech_lead"))
        reviews += 1
        if reviews == 1:
            async with agent_sessions.begin() as db:
                prompt = await db.scalar(
                    select(PromptVersion).where(PromptVersion.task_name == "director")
                )
                if change == "version":
                    prompt.version = "director_v8"
                elif change == "model":
                    prompt.model = "changed-model"
                else:
                    prompt.template = "실행 도중 바뀐 정책"
            failed = approved_review()
            failed["wording_valid" if mode == "auto" else "plan_valid"] = False
            return response(failed)
        return response(approved_review())

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
        )
        assert result.failure is not None and result.next_turn_id is None
        assert len(sent) == 3
        redis = Redis()
        with pytest.raises(AppError) as rejected:
            await retry(agent_sessions, agent_seed, redis, uuid4(), http)
        assert rejected.value.reason.value == "question_retry_unavailable"
        assert len(sent) == 3 and redis.calls == []
    async with agent_sessions() as db:
        row = await db.get(InterviewSession, agent_seed["interview_id"])
        saved = row.context_state["director_retry_inputs"]["2"]
        assert saved["analysis_reuse_prompt"] == {
            "task_name": "director",
            "version": "director_v10",
            "model": "db-model",
            "template": "질문 생성 fixture",
        }
        assert await availability(db, row) == (False, 0)
        turn = await db.get(InterviewTurn, result.turn_id)
        assert turn.answer_text == "팀원 담당입니다"
        assert turn.analysis == json.loads(json.dumps(asdict(original)))


async def test_empty_lookup_auto_recovery_keeps_same_policy_without_another_t3(
    agent_sessions, agent_seed
):
    await seed_version(agent_sessions, agent_seed, "director_v10")
    sent, reviews = [], 0

    async def handle(request):
        nonlocal reviews
        if request.url.host == "api.github.com":
            return httpx.Response(500)
        payload = json.loads(json.loads(request.content)["input"][0]["content"][0]["text"])
        sent.append(payload)
        if "answer" in payload:
            return response(asdict(requesting_analysis(agent_seed)))
        if payload["operation"] == "plan":
            return response(plan("tech_lead"))
        reviews += 1
        return response(
            {**approved_review(), "wording_valid": False} if reviews == 1 else approved_review()
        )

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
        )
    assert result.failure is None and result.next_turn_id is not None
    assert len(sent) == 5 and sum("answer" in payload for payload in sent) == 1
    assert all(payload["tool_results"][0]["status"] == "tool_error" for payload in sent[1:])
    async with agent_sessions() as db:
        row = await db.get(InterviewSession, agent_seed["interview_id"])
        assert (
            row.context_state["director_retry_inputs"]["2"]["analysis_reuse_prompt"]["version"]
            == "director_v10"
        )
