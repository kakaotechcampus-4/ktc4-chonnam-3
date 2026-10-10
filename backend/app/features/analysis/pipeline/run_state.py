"""분석의 원본 상태를 확정한 뒤 Redis에 알린다."""

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select

from app.core.logging import get_logger
from app.db.models.analysis import AnalysisJob

logger = get_logger(__name__)


def elapsed(start: datetime | None, end: datetime) -> int | None:
    return max(0, int((end - start).total_seconds() * 1000)) if start else None


async def notify(
    ctx: dict[str, Any], run_id: UUID, payload: dict[str, object], states: dict[str, str]
) -> None:
    try:
        async with ctx["redis"].pipeline(transaction=True) as pipe:
            # 문서 미첨부와 중도 실패의 skipped 상태도 종료 알림 전에 함께 반영한다.
            pipe.hset(f"run:{run_id}:steps", mapping=states)
            pipe.expire(f"run:{run_id}:steps", ctx["settings"].analysis_run_ttl_seconds)
            pipe.publish(f"run:{run_id}:events", json.dumps(payload))
            await pipe.execute()
    except Exception:
        # 알림 장애가 이미 commit된 분석 결과를 실패로 바꾸면 안 된다.
        logger.warning("analysis_notification_lost", run_id=str(run_id))


async def set_step(ctx: dict[str, Any], run_id: UUID, key: str, status: str) -> None:
    async with ctx["session_factory"].begin() as db:
        run = await db.scalar(select(AnalysisJob).where(AnalysisJob.id == run_id).with_for_update())
        if run is None or run.status != "running":
            return
        run.steps = [
            {**step, "status": status} if step["key"] == key else step for step in run.steps
        ]
        states = {str(item["key"]): str(item["status"]) for item in run.steps}
    await notify(ctx, run_id, {"type": "step", "step": key, "status": status}, states)


@asynccontextmanager
async def step(ctx: dict[str, Any], run_id: UUID, key: str) -> AsyncIterator[None]:
    await set_step(ctx, run_id, key, "running")
    yield
    await set_step(ctx, run_id, key, "completed")
