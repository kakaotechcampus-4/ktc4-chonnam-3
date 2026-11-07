"""준비 job 없이 preparing 으로 남은 면접을 다시 큐에 등록한다. 실행 중인 준비는 건드리지 않는다."""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from arq.connections import ArqRedis
from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.db.models import InterviewSession
from app.features.interview.queue import enqueue_interview_prep

PAGE_SIZE = 100
MAX_PAGES = 10  # 한 주기에 PAGE_SIZE * MAX_PAGES 건까지만 본다.


async def recover_unqueued_preparations(
    sessions: async_sessionmaker[AsyncSession],
    redis: ArqRedis,
    *,
    min_age_seconds: int,
    now: datetime | None = None,
) -> int:
    """오래된 미착수 preparing 면접을 재등록하고 등록을 확인한 개수를 돌려준다."""
    cutoff = (now or datetime.now(UTC)) - timedelta(seconds=min_age_seconds)
    registered = 0
    cursor: tuple[datetime, UUID] | None = None
    # 이미 큐에 있는 행은 updated_at 이 그대로라 앞쪽을 계속 차지한다.
    # keyset 으로 뒤쪽까지 순회한다.
    for _ in range(MAX_PAGES):
        query = (
            select(InterviewSession.id, InterviewSession.context_state, InterviewSession.updated_at)
            .where(InterviewSession.status == "preparing", InterviewSession.updated_at <= cutoff)
            .order_by(InterviewSession.updated_at, InterviewSession.id)
            .limit(PAGE_SIZE)
        )
        if cursor is not None:
            query = query.where(tuple_(InterviewSession.updated_at, InterviewSession.id) > cursor)
        async with sessions() as db:
            page = (await db.execute(query)).all()
        for interview_id, state, _updated_at in page:
            # claim 이 있으면 worker 가 잡았거나 lease 만료 reaper 의 대상이다.
            if isinstance(state, dict) and state.get("prepare_job_id") is not None:
                continue
            # 같은 _job_id 가 이미 큐·실행 중이면 새 job 이 생기지 않는다.
            if await enqueue_interview_prep(redis, interview_id):
                registered += 1
        if len(page) < PAGE_SIZE:
            break
        cursor = (page[-1].updated_at, page[-1].id)
    return registered


async def interview_prep_reaper(ctx: dict[str, Any]) -> None:
    settings = ctx.get("settings") or get_settings()
    await recover_unqueued_preparations(
        ctx["session_factory"],
        ctx["redis"],
        min_age_seconds=settings.interview_prep_reaper_min_age_seconds,
    )
