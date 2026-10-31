"""서로 다른 사용자가 공유하는 공고·프레임의 잠금 순서를 PG에서 검사한다."""

import asyncio

from devon_ai import contracts as c
from sqlalchemy import func, select

from app.db.models import DomainQuestionFrame, JobPosting
from app.features.interview.agent_context import load_context

LIMITS = c.ContextLimits(2, 0, "fixture")
QUOTA = {"tech_lead": 6, "domain_lead": 2, "hr_manager": 1}


async def test_context_locks_shared_posting_before_domain_frames(agent_sessions, agent_seed):
    # 다른 사용자의 준비 트랜잭션이 공유 공고를 먼저 잠근 상황을 만든다.
    async with agent_sessions() as preparation, agent_sessions() as reader:
        task = None
        try:
            await preparation.scalar(
                select(JobPosting)
                .where(JobPosting.id == agent_seed["posting_id"])
                .with_for_update()
            )
            preparation_pid = await preparation.scalar(select(func.pg_backend_pid()))
            reader_pid = await reader.scalar(select(func.pg_backend_pid()))
            task = asyncio.create_task(
                load_context(
                    reader,
                    user_id=agent_seed["owner"],
                    interview_id=agent_seed["interview_id"],
                    limits=LIMITS,
                    quota=QUOTA,
                    lock=True,
                )
            )
            # 실제 공고 잠금 대기를 확인해 스케줄러의 실행 타이밍에 의존하지 않는다.
            async with asyncio.timeout(5):
                async with agent_sessions() as observer:
                    while True:
                        blockers = await observer.scalar(select(func.pg_blocking_pids(reader_pid)))
                        if preparation_pid in blockers:
                            break
            frames = (
                await preparation.scalars(
                    select(DomainQuestionFrame)
                    .where(DomainQuestionFrame.id == agent_seed["frame_id"])
                    .with_for_update(nowait=True)
                )
            ).all()
            assert len(frames) == 1
            await preparation.commit()
            context = await asyncio.wait_for(task, 5)
            assert context.domain_frames[0].id == str(agent_seed["frame_id"])
        finally:
            await preparation.rollback()
            if task is not None:
                await asyncio.wait_for(task, 5)
            await reader.rollback()


async def test_readonly_context_leaves_shared_posting_and_frames_unlocked(
    agent_sessions, agent_seed
):
    async with agent_sessions() as preparation, agent_sessions() as reader:
        await preparation.scalar(
            select(JobPosting).where(JobPosting.id == agent_seed["posting_id"]).with_for_update()
        )
        context = await asyncio.wait_for(
            load_context(
                reader,
                user_id=agent_seed["owner"],
                interview_id=agent_seed["interview_id"],
                limits=LIMITS,
                quota=QUOTA,
                lock=False,
            ),
            5,
        )
        frame = await preparation.scalar(
            select(DomainQuestionFrame)
            .where(DomainQuestionFrame.id == agent_seed["frame_id"])
            .with_for_update(nowait=True)
        )
        assert frame is not None
        assert context.domain_frames[0].id == str(frame.id)
