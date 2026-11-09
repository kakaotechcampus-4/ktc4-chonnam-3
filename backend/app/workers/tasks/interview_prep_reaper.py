"""준비 job 없이 preparing 으로 남은 면접을 다시 큐에 등록한다. 실행 중인 준비는 건드리지 않는다."""

from contextlib import aclosing
from datetime import UTC, datetime, timedelta
from typing import Any

from arq.connections import ArqRedis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.db.models import InterviewSession
from app.features.interview.queue import enqueue_interview_prep
from app.workers.preparation_candidates import MAX_PAGES as DEFAULT_MAX_PAGES
from app.workers.preparation_candidates import PAGE_SIZE as DEFAULT_PAGE_SIZE
from app.workers.preparation_candidates import (
    PreparationScanState,
    preparing_candidates,
    scan_state,
)

PAGE_SIZE = DEFAULT_PAGE_SIZE
MAX_PAGES = DEFAULT_MAX_PAGES


async def recover_unqueued_preparations(
    sessions: async_sessionmaker[AsyncSession],
    redis: ArqRedis,
    *,
    min_age_seconds: int,
    now: datetime | None = None,
    state: PreparationScanState | None = None,
) -> int:
    """오래된 미착수 preparing 면접을 재등록하고 등록을 확인한 개수를 돌려준다."""
    cutoff = (now or datetime.now(UTC)) - timedelta(seconds=min_age_seconds)
    registered = 0
    # 기존 reaper의 페이지 설정을 공유 순회에도 전달해 주기별 상한과 keyset 계약을 유지한다.
    async with aclosing(
        preparing_candidates(
            sessions, cutoff=cutoff, state=state, page_size=PAGE_SIZE, max_pages=MAX_PAGES
        )
    ) as candidates:
        async for interview_id, context in candidates:
            # claim 이 있으면 worker 가 잡았거나 lease 만료 reaper 의 대상이다.
            if isinstance(context, dict) and context.get("prepare_job_id") is not None:
                continue
            async with sessions() as db:
                row = await db.scalar(
                    select(InterviewSession).where(
                        InterviewSession.id == interview_id,
                        InterviewSession.status == "preparing",
                        InterviewSession.updated_at <= cutoff,
                    )
                )
                # 후보 조회 뒤 claim·상태가 바뀐 행을 다시 등록하지 않는다.
                if row is None or (row.context_state or {}).get("prepare_job_id") is not None:
                    continue
            # DB 잠금 없이 큐에 접근한다. 이후 경쟁은 동일 job ID와 worker claim이 막는다.
            # 같은 _job_id 가 이미 큐·실행 중이면 새 job 이 생기지 않는다.
            if await enqueue_interview_prep(redis, interview_id):
                registered += 1
    return registered


async def interview_prep_reaper(ctx: dict[str, Any]) -> None:
    settings = ctx.get("settings") or get_settings()
    state = scan_state(ctx, "unqueued")
    if state.lock.locked():
        return
    async with state.lock:
        await recover_unqueued_preparations(
            ctx["session_factory"],
            ctx["redis"],
            min_age_seconds=settings.interview_prep_reaper_min_age_seconds,
            state=state,
        )
