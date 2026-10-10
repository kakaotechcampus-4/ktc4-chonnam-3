"""내부 진행 이벤트를 FE의 data/type/key SSE 계약으로 변환한다."""

import json
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

from arq.connections import ArqRedis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models.analysis import AnalysisJob
from app.features.analysis.events import RunSnapshot, StepState, stream_run_progress
from app.realtime.bus import RedisEventBus


async def analysis_events(
    sessions: async_sessionmaker[AsyncSession], redis: ArqRedis, run_id: UUID, user_id: UUID
) -> AsyncIterator[dict[str, Any]]:
    states: dict[str, str] = {}
    failure: str | None = None

    async def snapshot() -> RunSnapshot:
        nonlocal failure
        # 열린 SSE 연결이 DB 연결·트랜잭션을 계속 점유하지 않는다.
        async with sessions() as db:
            run = await db.scalar(
                select(AnalysisJob).where(
                    AnalysisJob.id == run_id,
                    AnalysisJob.user_id == user_id,
                    AnalysisJob.job_type == "analysis_run",
                )
            )
            if run is None:
                failure = "run_expired"
                return RunSnapshot(status="failed", steps=())
            failure = run.error_code
            steps = tuple(
                StepState(step=str(item["key"]), status=str(item["status"])) for item in run.steps
            )
            states.update({step.step: step.status for step in steps})
            return RunSnapshot(status=run.status, steps=steps)

    async for event in stream_run_progress(
        str(run_id), bus=RedisEventBus(redis), read_snapshot=snapshot
    ):
        data = json.loads(event["data"])
        kind = event["event"]
        if kind in {"completed", "failed"}:
            # terminal 알림만 도착해도 실패 단계와 skipped 상태까지 DB 원본으로 복원한다.
            previous = dict(states)
            final = await snapshot()
            for item in final.steps:
                if previous.get(item.step) != item.status:
                    yield {
                        "data": json.dumps(
                            {"type": "step", "key": item.step, "status": item.status}
                        )
                    }
            counted = [status for status in states.values() if status != "skipped"]
            value = round(100 * counted.count("completed") / len(counted)) if counted else 0
            yield {"data": json.dumps({"type": "progress", "value": value})}
        if kind == "step":
            states[data["step"]] = data["status"]
            payload = {"type": "step", "key": data["step"], "status": data["status"]}
        elif kind == "failed":
            payload = {
                "type": "failed",
                "reason": data.get("reason") or failure or "internal_error",
            }
        else:
            payload = {"type": "completed"}
        # event 필드를 생략해야 FE EventSource.onmessage가 수신한다.
        yield {"data": json.dumps(payload)}
        if kind == "step":
            counted = [status for status in states.values() if status != "skipped"]
            value = round(100 * counted.count("completed") / len(counted)) if counted else 0
            yield {"data": json.dumps({"type": "progress", "value": value})}
