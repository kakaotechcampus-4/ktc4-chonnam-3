"""결과 읽기끼리는 병행하되 run 작성과의 정합성은 공유 잠금으로 지킨다."""

import asyncio

import pytest
from sqlalchemy import select, text

from app.core.config import Settings
from app.db.models.analysis import AnalysisJob
from app.db.models.posting import JobPosting
from app.db.models.user import User
from app.features.analysis.service import get_result


async def seed_result(sessions):
    async with sessions.begin() as db:
        user = User(name="Result lock fixture")
        posting = JobPosting(
            normalized_url="https://www.wanted.co.kr/wd/1",
            raw_url="https://www.wanted.co.kr/wd/1",
            parse_status="succeeded",
            position="Before writer",
        )
        db.add_all([user, posting])
        await db.flush()
        run = AnalysisJob(
            user_id=user.id,
            job_posting_id=posting.id,
            job_type="analysis_run",
            status="succeeded",
        )
        db.add(run)
        await db.flush()
        return user.id, run.id, posting.id


async def test_result_reader_does_not_wait_for_another_reader(session_factory):
    user_id, run_id, _ = await seed_result(session_factory)
    async with session_factory() as first, session_factory() as second:
        await first.scalar(
            select(AnalysisJob).where(AnalysisJob.id == run_id).with_for_update(read=True)
        )
        # 서버 상한 안에서 두 번째 읽기도 끝나야 한다. 배타 잠금이면 DB가 거절한다.
        await second.execute(text("SET LOCAL lock_timeout = '250ms'"))
        response = await get_result(second, user_id, run_id, Settings(_env_file=None))
        assert response.position == "Before writer"
        assert response.repositories == []
        await first.rollback()


async def test_result_reader_waits_for_writer_and_reads_committed_result(session_factory):
    user_id, run_id, posting_id = await seed_result(session_factory)
    started = asyncio.Event()

    async def read():
        async with session_factory() as db:
            started.set()
            return await get_result(db, user_id, run_id, Settings(_env_file=None))

    reader = None
    async with session_factory() as writer:
        await writer.scalar(select(AnalysisJob).where(AnalysisJob.id == run_id).with_for_update())
        posting = await writer.get(JobPosting, posting_id)
        posting.position = "After writer"
        await writer.flush()
        try:
            reader = asyncio.create_task(read())
            await asyncio.wait_for(started.wait(), timeout=5)
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(asyncio.shield(reader), timeout=0.2)
        finally:
            await writer.commit()
            if reader is not None:
                response = await asyncio.wait_for(reader, timeout=5)
    assert response.position == "After writer"
