"""기존 설계의 queued run 큐 등록 복구. 실행 중인 작업은 다시 시작하지 않는다."""

from typing import Any

from sqlalchemy import select

from app.db.models.analysis import AnalysisJob
from app.features.analysis.queue import enqueue_analysis


async def recover_queued_runs(ctx: dict[str, Any]) -> None:
    async with ctx["session_factory"]() as db:
        runs = list(
            await db.scalars(
                select(AnalysisJob.id).where(
                    AnalysisJob.job_type == "analysis_run", AnalysisJob.status == "queued"
                )
            )
        )
    for run_id in runs:
        await enqueue_analysis(ctx["redis"], run_id)
