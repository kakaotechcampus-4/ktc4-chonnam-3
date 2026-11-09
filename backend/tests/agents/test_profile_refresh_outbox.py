

async def test_accepted_job_then_lost_enqueue_response_never_reverts_worker_ack(
    agent_sessions, agent_seed
):
    helper = api()
    rid = await request(agent_sessions, agent_seed, await seed_report(agent_sessions, agent_seed))

    async def accepted_then_disconnected(*args, **kwargs):
        token = await helper.claim(agent_sessions, rid, agent_seed["owner"], 1)
        assert token is not None
        assert await helper.finish(agent_sessions, rid, token, success=True)
        raise ConnectionError("response lost")

    redis = AsyncMock()
    redis.enqueue_job.side_effect = accepted_then_disconnected
    assert await helper.dispatch(agent_sessions, redis, rid) is False
    assert (await read(agent_sessions, rid)).status == "succeeded"
