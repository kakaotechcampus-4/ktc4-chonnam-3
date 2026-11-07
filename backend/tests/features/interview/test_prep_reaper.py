"""enqueue 가 유실된 preparing 면접을 reaper 가 복구한다. 실제 PostgreSQL·ARQ 로 검증한다."""

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from arq.jobs import Job, JobStatus
from sqlalchemy import update

from app.core.errors import AppError
from app.db.models import InterviewSession
from app.features.interview import prepare_lease, service
from app.features.interview.queue import enqueue_interview_prep
from app.shared.enums import Reason
from app.workers import analysis_app, arq_app
from app.workers.tasks import interview_prep_reaper as reaper_module
from app.workers.tasks.interview_prep_reaper import (
    interview_prep_reaper,
    recover_unqueued_preparations,
)
from app.workers.tasks.interview_preparation_reaper import recover_preparations

from .factories import make_repo, make_run, make_user
from .test_service import FakeRedis

MIN_AGE = 60


@pytest.fixture
async def lost(db, app):
    """enqueue 만 실패해 준비 job 없이 preparing 으로 남은 면접."""
    run = await make_run(db, await make_user(db))
    repo = await make_repo(db, run)
    interview_id, _ = await service.create_interview(
        db,
        FakeRedis(enqueue_fail=True),
        user_id=run.user_id,
        run_id=run.id,
        repository_ids=[repo.id],
    )
    return run, repo, interview_id


async def _lost_interview(db: Any) -> uuid.UUID:
    run = await make_run(db, await make_user(db))
    repo = await make_repo(db, run)
    interview_id, _ = await service.create_interview(
        db,
        FakeRedis(enqueue_fail=True),
        user_id=run.user_id,
        run_id=run.id,
        repository_ids=[repo.id],
    )
    return interview_id


async def _age(app: Any, interview_id: uuid.UUID, seconds: int, **values: Any) -> None:
    async with app.state.session_factory.begin() as db:
        await db.execute(
            update(InterviewSession)
            .where(InterviewSession.id == interview_id)
            .values(updated_at=datetime.now(UTC) - timedelta(seconds=seconds), **values)
        )


async def _recover(app: Any) -> int:
    return await recover_unqueued_preparations(
        app.state.session_factory, app.state.redis, min_age_seconds=MIN_AGE
    )


async def _status(app: Any, interview_id: uuid.UUID) -> JobStatus:
    return await Job(f"interview_prep:{interview_id}", app.state.redis).status()


async def test_enqueue_failure_leaves_row_and_reaper_registers_it(app, db, lost) -> None:
    _, _, interview_id = lost
    row = await db.get(InterviewSession, interview_id)
    assert row is not None and row.status == "preparing"
    await _age(app, interview_id, MIN_AGE + 5)

    assert await _recover(app) == 1

    job = Job(f"interview_prep:{interview_id}", app.state.redis)
    assert await job.status() == JobStatus.queued
    info = await job.info()
    assert info is not None and info.args == (str(interview_id),)


async def test_reaper_skips_young_preparing_row(app, lost) -> None:
    _, _, interview_id = lost
    await _age(app, interview_id, MIN_AGE - 30)
    assert await _recover(app) == 0
    assert await _status(app, interview_id) == JobStatus.not_found


@pytest.mark.parametrize("status", ["in_progress", "preparing_failed", "completed", "abandoned"])
async def test_reaper_leaves_non_preparing_rows(app, lost, status) -> None:
    _, _, interview_id = lost
    await _age(app, interview_id, MIN_AGE + 5, status=status)
    assert await _recover(app) == 0
    assert await _status(app, interview_id) == JobStatus.not_found


async def test_reaper_leaves_claimed_preparation_to_the_lease_reaper(app, lost) -> None:
    _, _, interview_id = lost
    await _age(app, interview_id, MIN_AGE + 5, context_state={"prepare_job_id": str(uuid.uuid4())})
    assert await _recover(app) == 0
    assert await _status(app, interview_id) == JobStatus.not_found


async def test_reaper_and_original_enqueue_never_duplicate_the_job(app, lost) -> None:
    _, _, interview_id = lost
    await _age(app, interview_id, MIN_AGE + 5)
    redis = app.state.redis

    assert await enqueue_interview_prep(redis, interview_id) is True  # 늦게 성공한 원래 enqueue
    assert await _recover(app) == 1  # 이미 큐에 있으면 새 job 을 만들지 않는다.
    assert await _recover(app) == 1
    assert await redis.zcard(redis.default_queue_name) == 1


async def test_reaper_does_not_restart_a_running_job(app, lost) -> None:
    _, _, interview_id = lost
    await _age(app, interview_id, MIN_AGE + 5)
    redis = app.state.redis
    identity = f"interview_prep:{interview_id}"
    assert await enqueue_interview_prep(redis, interview_id) is True
    # worker 가 가져가 실행 중인 상태: 큐에서 빠지고 실행 표식이 있다.
    await redis.zrem(redis.default_queue_name, identity)
    await redis.set(f"arq:in-progress:{identity}", b"1", ex=60)

    assert await _status(app, interview_id) == JobStatus.in_progress
    assert await _recover(app) == 1
    assert await redis.zcard(redis.default_queue_name) == 0


async def test_reaper_reaches_lost_rows_behind_an_already_queued_page(
    app, db, lost, monkeypatch
) -> None:
    """앞 페이지가 이미 큐에 있는 행으로 가득 차도 뒤쪽 유실 행을 재등록한다."""
    monkeypatch.setattr(reaper_module, "PAGE_SIZE", 2)
    _, _, last_id = lost
    queued_ids = [await _lost_interview(db), await _lost_interview(db)]
    for offset, interview_id in enumerate(queued_ids):
        await _age(app, interview_id, MIN_AGE + 500 - offset)
        assert await enqueue_interview_prep(app.state.redis, interview_id) is True
    await _age(app, last_id, MIN_AGE + 5)

    assert await _recover(app) == 3
    assert await _status(app, last_id) == JobStatus.queued
    assert await app.state.redis.zcard(app.state.redis.default_queue_name) == 3


async def test_reaper_stops_after_max_pages(app, db, lost, monkeypatch) -> None:
    monkeypatch.setattr(reaper_module, "PAGE_SIZE", 1)
    monkeypatch.setattr(reaper_module, "MAX_PAGES", 2)
    _, _, newest_id = lost
    older_ids = [await _lost_interview(db), await _lost_interview(db)]
    for offset, interview_id in enumerate(older_ids):
        await _age(app, interview_id, MIN_AGE + 500 - offset)
    await _age(app, newest_id, MIN_AGE + 5)

    assert await _recover(app) == 2
    assert await _status(app, newest_id) == JobStatus.not_found


async def test_enqueue_window_is_bounded_by_the_lease_reaper_expiry(app, lost) -> None:
    """claim 없는 preparing 은 60초 뒤 재등록되고, 600초가 지나면 기존 reaper 가 실패 처리한다."""
    _, _, interview_id = lost
    await _age(app, interview_id, MIN_AGE + 1)
    assert await recover_preparations(app.state.session_factory) == 0
    assert await _recover(app) == 1
    assert await _status(app, interview_id) == JobStatus.queued

    await _age(app, interview_id, prepare_lease.JOB_TIMEOUT_SECONDS + 1)
    assert await recover_preparations(app.state.session_factory) == 1
    async with app.state.session_factory() as session:
        row = await session.get(InterviewSession, interview_id)
        assert row is not None and row.status == "preparing_failed"
    assert await _recover(app) == 0  # 실패 처리된 행은 새 reaper 의 대상이 아니다.


async def test_cron_entry_reads_threshold_from_settings(app, lost) -> None:
    _, _, interview_id = lost
    await _age(app, interview_id, 5)
    ctx = {
        "session_factory": app.state.session_factory,
        "redis": app.state.redis,
        "settings": SimpleNamespace(interview_prep_reaper_min_age_seconds=1),
    }
    await interview_prep_reaper(ctx)
    assert await _status(app, interview_id) == JobStatus.queued


async def test_recovered_run_does_not_block_a_new_interview(app, db, lost) -> None:
    """복구 전에는 활성 면접으로 막히고, 준비가 닫히면 같은 run 의 새 면접이 만들어진다."""
    run, repo, interview_id = lost
    user_id, run_id, repo_id = run.user_id, run.id, repo.id
    with pytest.raises(AppError) as exc:
        await service.create_interview(
            db, FakeRedis(), user_id=user_id, run_id=run_id, repository_ids=[repo_id]
        )
    assert exc.value.reason == Reason.SESSION_LIMIT_EXCEEDED

    await _age(app, interview_id, MIN_AGE + 5)
    assert await _recover(app) == 1
    async with app.state.session_factory.begin() as session:
        row = await session.get(InterviewSession, interview_id)
        assert row is not None
        prepare_lease.failed(row, "preparation_failed", "analyze_repo")

    new_id, _ = await service.create_interview(
        db, FakeRedis(), user_id=user_id, run_id=run_id, repository_ids=[repo_id]
    )
    assert new_id != interview_id


def test_worker_registers_reaper_cron_and_default_threshold() -> None:
    from app.core.config import Settings

    assert Settings.model_fields["interview_prep_reaper_min_age_seconds"].default == 60
    for worker in (arq_app.WorkerSettings, analysis_app.WorkerSettings):
        crons = [job for job in worker.cron_jobs if job.coroutine is interview_prep_reaper]
        assert len(crons) == 1 and crons[0].second == {0, 30}
