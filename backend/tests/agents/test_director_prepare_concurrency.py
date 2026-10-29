"""공통 입력을 사용하는 두 실제 준비 실행의 저장 경계를 함께 통과시킨다."""

import asyncio
from uuid import uuid4

from sqlalchemy import select

from app.db.models import (
    AnalysisJob,
    AnalysisRepoCandidate,
    InterviewSession,
    InterviewTurn,
    SessionRepository,
)
from tests.agents.test_director_prepare import Transport, run
from tests.agents.test_director_prepare import ready as ready


async def test_parallel_preparations_share_inputs_without_lock_upgrade(agent_sessions, ready):
    second_id, run_id = uuid4(), uuid4()
    async with agent_sessions.begin() as db:
        original = await db.get(InterviewSession, ready["interview_id"])
        candidate = await db.scalar(select(AnalysisRepoCandidate))
        db.add(
            AnalysisJob(
                id=run_id,
                user_id=ready["owner"],
                job_type="analysis_run",
                status="succeeded",
                job_posting_id=original.job_posting_id,
            )
        )
        await db.flush()
        db.add_all(
            [
                InterviewSession(
                    id=second_id,
                    user_id=ready["owner"],
                    analysis_job_id=run_id,
                    job_posting_id=original.job_posting_id,
                    status="preparing",
                ),
                AnalysisRepoCandidate(
                    analysis_job_id=run_id,
                    repository_id=candidate.repository_id,
                    base_rank=1,
                    batch_no=1,
                    batch_rank=1,
                    filter_status="eligible",
                    ranking_signals=candidate.ranking_signals,
                ),
            ]
        )
        await db.flush()
        db.add(
            SessionRepository(
                interview_session_id=second_id,
                repository_id=ready["repo_id"],
                snapshot_head_sha=ready["sha"],
                is_primary=True,
            )
        )
    reached, both = 0, asyncio.Event()

    def synchronized(seed):
        transport = Transport(seed)
        entered = False

        async def exchange(request):
            nonlocal reached, entered
            if request.method == "POST" and not entered:
                entered = True
                reached += 1
                if reached == 2:
                    both.set()
                await asyncio.wait_for(both.wait(), 20)
            return await transport(request)

        return exchange

    second = {**ready, "interview_id": second_id}
    assert await asyncio.wait_for(
        asyncio.gather(
            run(agent_sessions, ready, synchronized(ready)),
            run(agent_sessions, second, synchronized(second)),
        ),
        30,
    ) == [True, True]
    async with agent_sessions() as db:
        assert len((await db.scalars(select(InterviewTurn))).all()) == 2
