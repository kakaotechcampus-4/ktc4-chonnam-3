"""실제 DB·Redis로 커밋 경계와 전체 단계 mirror를 검증한다."""

import json
from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.db.models.analysis import AnalysisJob
from app.features.analysis.pipeline.run_completion import finish_run
from app.features.analysis.pipeline.run_state import set_step
from app.realtime.bus import RedisEventBus
from tests.features.test_analysis_api import member as member

INITIAL = {
    "doc_extract": "skipped",
    "repo_select": "pending",
    "repo_detail": "pending",
    "jd_fetch": "pending",
    "jd_extract": "pending",
    "repo_analyze": "pending",
    "match_score": "pending",
}


@pytest.fixture
async def running_run(client, member, db):
    response = await client.post(
        "/api/analysis-runs", json={"postingUrl": "https://wanted.co.kr/wd/1"}
    )
    assert response.status_code == 202
    run = await db.get(AnalysisJob, UUID(response.json()["runId"]))
    run.status, run.started_at = "running", datetime.now(UTC)
    await db.commit()
    return run.id


def _context(app):
    return {
        "session_factory": app.state.session_factory,
        "redis": app.state.redis,
        "settings": app.state.settings,
    }


async def _stored(app, run_id):
    # 워커가 사용한 session의 메모리 상태가 아니라 다른 연결의 가시성을 확인한다.
    async with app.state.session_factory() as session:
        run = await session.get(AnalysisJob, run_id)
        return run.status, {item["key"]: item["status"] for item in run.steps}


async def _mirror(redis, run_id):
    return {
        key.decode(): value.decode()
        for key, value in (await redis.hgetall(f"run:{run_id}:steps")).items()
    }


def _observe_execution(app, monkeypatch, run_id):
    observations = []
    pipeline = app.state.redis.pipeline

    def observed_pipeline(*args, **kwargs):
        pipe = pipeline(*args, **kwargs)
        execute = pipe.execute

        async def observed_execute(*args, **kwargs):
            commands = [command[0] for command, _ in pipe.command_stack]
            observations.append((await _stored(app, run_id), commands))
            return await execute(*args, **kwargs)

        pipe.execute = observed_execute
        return pipe

    monkeypatch.setattr(app.state.redis, "pipeline", observed_pipeline)
    return observations


async def test_first_step_publishes_committed_state_and_mirrors_document_skip(
    app, running_run, monkeypatch
):
    observations = _observe_execution(app, monkeypatch, running_run)
    expected = {**INITIAL, "repo_select": "running"}
    redis = app.state.redis
    async with RedisEventBus(redis).subscribe(f"run:{running_run}:events") as subscription:
        await set_step(_context(app), running_run, "repo_select", "running")
        message = await subscription.get_message(timeout=1)
        assert message is not None
        assert json.loads(message["data"]) == {
            "type": "step",
            "step": "repo_select",
            "status": "running",
        }
        assert observations == [(("running", expected), ["HSET", "EXPIRE", "PUBLISH"])]
        assert await _mirror(redis, running_run) == expected
        assert (
            0
            < await redis.ttl(f"run:{running_run}:steps")
            <= (app.state.settings.analysis_run_ttl_seconds)
        )


async def test_failure_mirrors_failed_and_skipped_steps_before_terminal_event(
    app, running_run, monkeypatch
):
    await set_step(_context(app), running_run, "jd_fetch", "running")
    observations = _observe_execution(app, monkeypatch, running_run)
    expected = {key: "failed" if key == "jd_fetch" else "skipped" for key in INITIAL}
    redis = app.state.redis
    async with RedisEventBus(redis).subscribe(f"run:{running_run}:events") as subscription:
        await finish_run(_context(app), running_run, "failed", "jd_fetch_failed")
        message = await subscription.get_message(timeout=1)
        assert message is not None
        assert json.loads(message["data"]) == {"type": "failed", "reason": "jd_fetch_failed"}
        assert observations == [(("failed", expected), ["HSET", "EXPIRE", "PUBLISH"])]
        assert await _mirror(redis, running_run) == expected


@pytest.mark.parametrize("status,error", [("succeeded", None), ("partial", "rate_limited")])
async def test_terminal_event_restores_an_empty_mirror(app, db, running_run, status, error):
    expected = {key: "skipped" if key == "doc_extract" else "completed" for key in INITIAL}
    run = await db.get(AnalysisJob, running_run)
    run.steps = [{"key": key, "status": value} for key, value in expected.items()]
    await db.commit()
    redis = app.state.redis
    async with RedisEventBus(redis).subscribe(f"run:{running_run}:events") as subscription:
        await finish_run(_context(app), running_run, status, error)
        message = await subscription.get_message(timeout=1)
        assert message is not None
        assert json.loads(message["data"]) == (
            {"type": "completed"}
            if status == "succeeded"
            else {"type": "failed", "reason": "rate_limited"}
        )
        assert await _stored(app, running_run) == (status, expected)
        assert await _mirror(redis, running_run) == expected
        assert (
            0
            < await redis.ttl(f"run:{running_run}:steps")
            <= (app.state.settings.analysis_run_ttl_seconds)
        )


@pytest.mark.parametrize("terminal", [False, True])
async def test_commit_failure_does_not_change_mirror_or_publish(app, running_run, terminal):
    redis = app.state.redis
    await redis.hset(f"run:{running_run}:steps", mapping=INITIAL)

    def reject_commit(session):
        raise RuntimeError("commit unavailable")

    async with RedisEventBus(redis).subscribe(f"run:{running_run}:events") as subscription:
        # 커밋 훅만 실패시키고 실제 조회·트랜잭션 rollback·Redis 구독은 유지한다.
        event.listen(Session, "before_commit", reject_commit)
        try:
            with pytest.raises(RuntimeError, match="commit unavailable"):
                if terminal:
                    await finish_run(_context(app), running_run, "failed", "internal_error")
                else:
                    await set_step(_context(app), running_run, "repo_select", "running")
        finally:
            event.remove(Session, "before_commit", reject_commit)
        assert await _stored(app, running_run) == ("running", INITIAL)
        assert await _mirror(redis, running_run) == INITIAL
        assert await subscription.get_message(timeout=0.05) is None


@pytest.mark.parametrize("status,error", [("succeeded", None), ("failed", "jd_fetch_failed")])
async def test_redis_execute_failure_preserves_committed_result(
    app, db, running_run, monkeypatch, status, error
):
    expected = dict.fromkeys(INITIAL, "skipped")
    if status == "succeeded":
        expected = {key: "skipped" if key == "doc_extract" else "completed" for key in INITIAL}
        run = await db.get(AnalysisJob, running_run)
        run.steps = [{"key": key, "status": value} for key, value in expected.items()]
        await db.commit()
    redis = app.state.redis
    await redis.hset(f"run:{running_run}:steps", mapping=INITIAL)
    pipeline = redis.pipeline

    def unavailable_pipeline(*args, **kwargs):
        pipe = pipeline(*args, **kwargs)

        async def unavailable_execute(*args, **kwargs):
            raise ConnectionError("redis unavailable")

        pipe.execute = unavailable_execute
        return pipe

    monkeypatch.setattr(redis, "pipeline", unavailable_pipeline)
    async with RedisEventBus(redis).subscribe(f"run:{running_run}:events") as subscription:
        await finish_run(_context(app), running_run, status, error)
        assert await _stored(app, running_run) == (status, expected)
        assert await _mirror(redis, running_run) == INITIAL
        assert await subscription.get_message(timeout=0.05) is None
