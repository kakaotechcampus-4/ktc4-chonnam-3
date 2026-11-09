"""준비 복구 후보를 고정된 기준 시각과 제한된 keyset 페이지로 순회한다."""

import asyncio
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import InterviewSession

PAGE_SIZE = 100
MAX_PAGES = 10


@dataclass
class PreparationScanState:
    cutoff: datetime | None = None
    cursor: tuple[datetime, UUID] | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


def scan_state(ctx: dict[str, Any], name: str) -> PreparationScanState:
    # ARQ가 job마다 복사하는 바깥 ctx 대신 startup에서 만든 내부 dict를 공유한다.
    states = ctx.setdefault("preparation_scan_states", {})
    state = states.setdefault(name, PreparationScanState())
    if not isinstance(state, PreparationScanState):
        raise TypeError("preparation scan state has an invalid type")
    return state


async def preparing_candidates(
    sessions: async_sessionmaker[AsyncSession],
    *,
    cutoff: datetime,
    state: PreparationScanState | None = None,
    page_size: int = PAGE_SIZE,
    max_pages: int = MAX_PAGES,
) -> AsyncGenerator[tuple[UUID, Any], None]:
    state = state or PreparationScanState()
    if state.cutoff is None:
        state.cutoff = cutoff
    for _ in range(max_pages):
        query = select(
            InterviewSession.id, InterviewSession.updated_at, InterviewSession.context_state
        ).where(InterviewSession.status == "preparing", InterviewSession.updated_at <= state.cutoff)
        if state.cursor is not None:
            query = query.where(
                tuple_(InterviewSession.updated_at, InterviewSession.id) > state.cursor
            )
        async with sessions() as db:
            rows = (
                await db.execute(
                    query.order_by(InterviewSession.updated_at, InterviewSession.id).limit(
                        page_size
                    )
                )
            ).all()
        # 후보 조회 트랜잭션은 외부 큐 요청·행 잠금 전에 닫는다.
        for interview_id, updated_at, context in rows:
            yield interview_id, context
            # 처리 중 취소되면 해당 행부터 다시 확인해 작업을 건너뛰지 않는다.
            state.cursor = updated_at, interview_id
        if len(rows) < page_size:
            state.cutoff = None
            state.cursor = None
            return
    # 한 주기의 상한에 도달하면 다음 cron이 같은 cutoff·cursor에서 이어간다.
