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
    async with sessions() as db:
        candidates = (
            await db.execute(
                select(
                    InterviewSession.id,
                    InterviewSession.context_state,
                )
                .where(
                    InterviewSession.status == "preparing",
                )
                .order_by(InterviewSession.updated_at)
                .limit(100)
            )
        ).all()
    for interview_id, state in candidates:
        state = state if isinstance(state, dict) else {}
        owner, call_id = state.get("prepare_job_id"), state.get("prepare_director_call_id")
        async with sessions.begin() as db:
            # Director 저장과 같은 record→interview 순서로 잠그고 owner를 다시 확인한다.
            query = (
                select(LLMCallRecord)
                .where(
                    LLMCallRecord.interview_session_id == interview_id,
                    LLMCallRecord.task_name == "director",
                    LLMCallRecord.turn_no == 1,
                )
                .order_by(LLMCallRecord.id)
                .with_for_update()
            )
            if call_id is not None:
                try:
                    query = query.where(LLMCallRecord.id == UUID(str(call_id)))
                except ValueError:
                    # 손상된 이전 marker도 만료 행의 회수 자체를 막지 않는다.
                    pass
            # call id가 없던 이전 claim은 같은 면접 첫 Director의 pending만 회수한다.
            records = (await db.scalars(query)).all()
            row = await db.scalar(
                select(InterviewSession)
                .where(
                    InterviewSession.id == interview_id,
                )
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if (
                row is None
                or row.status != "preparing"
                or (row.context_state or {}).get("prepare_job_id") != owner
                or (row.context_state or {}).get("prepare_director_call_id") != call_id
                or prepare_lease.expires(row) > now
            ):
                continue
            for record in records:
                if not (record.turn_id or record.failure or record.discard_reason):
                    record.discard_reason = "preparation_lease_expired"
            step = prepare_lease.STEPS[prepare_lease.completed(row)]
            prepare_lease.failed(row, "preparation_lease_expired", step)
            recovered += 1
    return recovered


async def interview_preparation_reaper(ctx: dict[str, Any]) -> None:
    await recover_preparations(ctx["session_factory"])
