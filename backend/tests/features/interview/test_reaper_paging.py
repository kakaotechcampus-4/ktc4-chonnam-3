"""첫 페이지의 비대상 준비 작업이 뒤의 복구 대상을 가리지 않아야 한다."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from arq.jobs import Job, JobStatus

from app.db.models import AnalysisJob, InterviewSession, JobPosting, User
from app.workers.tasks import interview_prep_reaper as enqueue_module
from app.workers.tasks import interview_preparation_reaper as lease_module
from app.workers.tasks.interview_prep_reaper import (
    interview_prep_reaper,
    recover_unqueued_preparations,
)
from app.workers.tasks.interview_preparation_reaper import (
    interview_preparation_reaper,
    recover_preparations,
)


async def _seed(db, *, claimed_first: bool, same_timestamp: bool, count: int = 101):
    now = datetime.now(UTC)
    user = User(name="isolated reaper pagination")
    posting = JobPosting(
        normalized_url=f"https://www.wanted.co.kr/wd/{uuid4().int}",
        raw_url="https://www.wanted.co.kr/wd/1",
        parse_status="succeeded",
    )
    db.add_all([user, posting])
    await db.flush()
    rows = []
    for index in range(count):
        run = AnalysisJob(
            id=uuid4(),
            user_id=user.id,
            job_type="analysis_run",
            status="succeeded",
            job_posting_id=posting.id,
        )
        db.add(run)
        await db.flush()
        target = index == count - 1
        state = {}
        if claimed_first and not target:
            state = {
                "prepare_job_id": str(uuid4()),
                "prepare_lease_expires_at": (now + timedelta(seconds=30)).isoformat(),
            }
        if not claimed_first and target:
            state = {
                "prepare_job_id": str(uuid4()),
                "prepare_lease_expires_at": (now - timedelta(seconds=1)).isoformat(),
            }
        updated = now - timedelta(minutes=5)
        if target and not same_timestamp:
            updated = now - timedelta(seconds=65)
        row = InterviewSession(
            id=UUID(int=index + 1),
            user_id=user.id,
            analysis_job_id=run.id,
            job_posting_id=posting.id,
            status="preparing",
            context_state=state,
            updated_at=updated,
        )
        db.add(row)
        rows.append(row.id)
    await db.commit()
    return rows, now


@pytest.mark.parametrize("same_timestamp", [False, True])
async def test_expired_lease_after_first_hundred_is_recovered(app, db, same_timestamp):
    rows, now = await _seed(db, claimed_first=False, same_timestamp=same_timestamp)

    assert await recover_preparations(app.state.session_factory, now=now) == 1

    await db.rollback()
    assert (await db.get(InterviewSession, rows[-1])).status == "preparing_failed"
    assert (await db.get(InterviewSession, rows[0])).status == "preparing"
    assert await recover_preparations(app.state.session_factory, now=now) == 0


@pytest.mark.parametrize("same_timestamp", [False, True])
async def test_unqueued_after_hundred_claimed_rows_is_registered(app, db, same_timestamp):
    rows, now = await _seed(db, claimed_first=True, same_timestamp=same_timestamp)

    assert (
        await recover_unqueued_preparations(
            app.state.session_factory, app.state.redis, min_age_seconds=60, now=now
        )
        == 1
    )

    job = Job(f"interview_prep:{rows[-1]}", app.state.redis)
    assert await job.status() == JobStatus.queued
    assert await app.state.redis.zcard(app.state.redis.default_queue_name) == 1


@pytest.mark.parametrize("phase", ["lease", "unqueued"])
async def test_shared_state_crosses_the_thousand_row_limit_on_the_next_cron(app, db, phase):
    rows, _ = await _seed(db, claimed_first=phase == "unqueued", same_timestamp=True, count=1001)
    shared = {
        "session_factory": app.state.session_factory,
        "redis": app.state.redis,
        "settings": app.state.settings,
        "preparation_scan_states": {},
    }
    cron = interview_prep_reaper if phase == "unqueued" else interview_preparation_reaper
    # 실제 ARQ처럼 top-level ctx는 복사하고 startup에서 만든 중첩 상태만 공유한다.
    await cron({**shared, "job_id": "first-cron"})
    await db.rollback()
    assert (await db.get(InterviewSession, rows[-1])).status == "preparing"
    if phase == "unqueued":
        assert (
            await Job(f"interview_prep:{rows[-1]}", app.state.redis).status() == JobStatus.not_found
        )

    await cron({**shared, "job_id": "second-cron"})
    await db.rollback()
    if phase == "lease":
        assert (await db.get(InterviewSession, rows[-1])).status == "preparing_failed"
    else:
        assert await Job(f"interview_prep:{rows[-1]}", app.state.redis).status() == JobStatus.queued


@pytest.mark.parametrize("phase", ["lease", "unqueued"])
async def test_cancelled_cron_releases_lock_and_revisits_the_unfinished_row(
    app, db, monkeypatch, phase
):
    rows, _ = await _seed(db, claimed_first=phase == "unqueued", same_timestamp=True)
    reached = asyncio.Event()
    calls = 0
    module = enqueue_module if phase == "unqueued" else lease_module
    name = "enqueue_interview_prep" if phase == "unqueued" else "_recover_one"
    original = getattr(module, name)

    async def blocked(*args, **kwargs):
        nonlocal calls
        if args[1] == rows[-1]:
            calls += 1
            reached.set()
            await asyncio.Event().wait()
        return await original(*args, **kwargs)

    monkeypatch.setattr(module, name, blocked)
    shared = {
        "session_factory": app.state.session_factory,
        "redis": app.state.redis,
        "settings": app.state.settings,
        "preparation_scan_states": {},
    }
    cron = interview_prep_reaper if phase == "unqueued" else interview_preparation_reaper
    task = asyncio.create_task(cron({**shared, "job_id": "cancelled"}))
    await asyncio.wait_for(reached.wait(), 10)
    # 겹친 cron은 진행 중인 cursor를 움직이지 않는다.
    await asyncio.wait_for(cron({**shared, "job_id": "overlapping"}), 2)
    assert calls == 1
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not shared["preparation_scan_states"][phase].lock.locked()
    monkeypatch.setattr(module, name, original)
    await cron({**shared, "job_id": "recovery"})
    await db.rollback()
    if phase == "lease":
        assert (await db.get(InterviewSession, rows[-1])).status == "preparing_failed"
    else:
        assert await Job(f"interview_prep:{rows[-1]}", app.state.redis).status() == JobStatus.queued


async def test_reenqueue_rechecks_claim_after_candidate_snapshot(app, db, monkeypatch):
    rows, now = await _seed(db, claimed_first=True, same_timestamp=True, count=1)

    async def claimed_after_scan(*args, **kwargs):
        async with app.state.session_factory.begin() as fresh:
            row = await fresh.get(InterviewSession, rows[-1], with_for_update=True)
            row.context_state = {
                "prepare_job_id": "new-owner",
                "prepare_lease_expires_at": (now + timedelta(seconds=90)).isoformat(),
            }
        yield rows[-1], {}

    monkeypatch.setattr(enqueue_module, "preparing_candidates", claimed_after_scan)
    assert (
        await recover_unqueued_preparations(
            app.state.session_factory, app.state.redis, min_age_seconds=60, now=now
        )
        == 0
    )
    assert await Job(f"interview_prep:{rows[-1]}", app.state.redis).status() == JobStatus.not_found
