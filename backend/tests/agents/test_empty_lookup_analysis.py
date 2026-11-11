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
