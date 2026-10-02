"""큐 알림 유실과 실제 실행 상태를 구분해 중복 분석을 막는다."""

from uuid import UUID

import pytest
from arq.jobs import Job, JobStatus

from app.db.models.analysis import AnalysisJob
from app.workers.tasks.analysis_reaper import analysis_reaper
from tests.features.test_analysis_api import member as member


async def test_reaper_restores_only_queued_runs(client, member, app, db):
    response = await client.post(
        "/api/analysis-runs", json={"postingUrl": "https://wanted.co.kr/wd/1"}
    )
    run_id = response.json()["runId"]
    await app.state.redis.flushdb()
    ctx = {
        "session_factory": app.state.session_factory,
        "redis": app.state.redis,
        "settings": app.state.settings,
    }
    await analysis_reaper(ctx)
    assert await Job(f"analysis_run:{run_id}", app.state.redis).status() == JobStatus.queued
    run = await db.get(AnalysisJob, UUID(run_id))
    run.status = "running"
    await db.commit()
    await app.state.redis.flushdb()
    await analysis_reaper(ctx)
    assert await Job(f"analysis_run:{run_id}", app.state.redis).status() == JobStatus.not_found


@pytest.mark.parametrize("residue", ["orphan_payload", "retained_result"])
async def test_reaper_recovers_unrunnable_arq_residue(client, member, app, residue):
    response = await client.post(
        "/api/analysis-runs", json={"postingUrl": "https://wanted.co.kr/wd/1"}
    )
    run_id = response.json()["runId"]
    identity = f"analysis_run:{run_id}"
    await app.state.redis.zrem(app.state.redis.default_queue_name, identity)
    if residue == "retained_result":
        await app.state.redis.delete(f"arq:job:{identity}")
        await app.state.redis.set(f"arq:result:{identity}", b"stale-result", ex=3600)
    await app.state.redis.set(f"arq:retry:{identity}", 1, ex=3600)
    await analysis_reaper({"session_factory": app.state.session_factory, "redis": app.state.redis})
    assert await Job(identity, app.state.redis).status() == JobStatus.queued
    assert not await app.state.redis.exists(f"arq:retry:{identity}")
