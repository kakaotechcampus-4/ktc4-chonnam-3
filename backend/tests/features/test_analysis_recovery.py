"""생성 API 없이 실제 DB·ARQ로 대기 run 복구와 잔여 키 처리를 검증한다."""

import pytest
from arq.jobs import Job, JobStatus

from app.db.models.analysis import AnalysisJob
from app.db.models.user import User
from app.features.analysis.queue import enqueue_analysis
from app.features.analysis.recovery import recover_queued_runs


@pytest.fixture
async def queued_run(db):
    user = User(name="큐 복구 검증")
    db.add(user)
    await db.flush()
    run = AnalysisJob(user_id=user.id, job_type="analysis_run", status="queued")
    db.add(run)
    await db.commit()
    return run


def _context(app):
    return {"session_factory": app.state.session_factory, "redis": app.state.redis}


async def test_reaper_restores_only_queued_runs(queued_run, app, db):
    identity = f"analysis_run:{queued_run.id}"
    await recover_queued_runs(_context(app))
    assert await Job(identity, app.state.redis).status() == JobStatus.queued
    info = await Job(identity, app.state.redis).info()
    assert info.function == "analysis_run" and info.args == (str(queued_run.id),)
    queued_run.status = "running"
    await db.commit()
    await app.state.redis.flushdb()
    await recover_queued_runs(_context(app))
    assert await Job(identity, app.state.redis).status() == JobStatus.not_found


@pytest.mark.parametrize("residue", ["orphan_payload", "retained_result"])
async def test_reaper_recovers_unrunnable_arq_residue(queued_run, app, residue):
    await enqueue_analysis(app.state.redis, queued_run.id)
    identity = f"analysis_run:{queued_run.id}"
    await app.state.redis.zrem(app.state.redis.default_queue_name, identity)
    if residue == "retained_result":
        await app.state.redis.delete(f"arq:job:{identity}")
        await app.state.redis.set(f"arq:result:{identity}", b"stale-result", ex=3600)
    await app.state.redis.set(f"arq:retry:{identity}", 1, ex=3600)
    await recover_queued_runs(_context(app))
    assert await Job(identity, app.state.redis).status() == JobStatus.queued
    assert not await app.state.redis.exists(f"arq:retry:{identity}")


@pytest.mark.parametrize("status", ["succeeded", "partial", "failed", "canceled"])
async def test_reaper_never_restarts_terminal_run(queued_run, app, db, status):
    queued_run.status = status
    await db.commit()
    await recover_queued_runs(_context(app))
    assert (
        await Job(f"analysis_run:{queued_run.id}", app.state.redis).status() == JobStatus.not_found
    )


async def test_reaper_does_not_register_initial_sync_as_analysis(queued_run, app, db):
    queued_run.job_type = "initial_sync"
    await db.commit()
    await recover_queued_runs(_context(app))
    assert await app.state.redis.zcard(app.state.redis.default_queue_name) == 0
