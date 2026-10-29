"""새 큐 메시지가 없어도 만료된 면접 준비를 재시도 가능한 실패로 회수한다."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import InterviewSession, LLMCallRecord
from app.features.interview import prepare_lease


async def recover_preparations(
    sessions: async_sessionmaker[AsyncSession], *, now: datetime | None = None
) -> int:
    recovered = 0
    now = now or datetime.now(UTC)
    async with sessions.begin() as db:
        rows = (
            await db.scalars(
                select(InterviewSession)
                .where(
                    InterviewSession.status == "preparing",
                    InterviewSession.context_state["prepare_job_id"].as_string().is_not(None),
                )
                .order_by(InterviewSession.updated_at)
                .limit(100)
                .with_for_update(skip_locked=True)
            )
        ).all()
        for row in rows:
            if prepare_lease.expires(row) > now:
                continue
            call_id = (row.context_state or {}).get("prepare_director_call_id")
            try:
                record = (
                    await db.get(LLMCallRecord, UUID(call_id)) if isinstance(call_id, str) else None
                )
            except ValueError:
                record = None
            if (
                record is not None
                and record.interview_session_id == row.id
                and record.task_name == "director"
                and record.turn_no == 1
                and not (record.turn_id or record.failure or record.discard_reason)
            ):
                # 동일 owner가 남긴 정확한 pending 기록만 닫아 새 첫 질문을 막지 않는다.
                record.discard_reason = "preparation_lease_expired"
            step = prepare_lease.STEPS[prepare_lease.completed(row)]
            prepare_lease.failed(row, "preparation_lease_expired", step)
            recovered += 1
    return recovered


async def interview_preparation_reaper(ctx: dict[str, Any]) -> None:
    await recover_preparations(ctx["session_factory"])
