"""DB에만 남은 대기 작업을 복구한다. 실행 중인 작업은 자동 재실행하지 않는다."""

from typing import Any

from sqlalchemy import select

from app.db.models.analysis import AnalysisJob, AnalysisRepoCandidatePage
from app.features.analysis.queue import enqueue_analysis
from app.features.analysis.recovery import recover_queued_runs


async def analysis_reaper(ctx: dict[str, Any]) -> None:
    await recover_queued_runs(ctx)
    async with ctx["session_factory"]() as db:
        pages = list(
            (
                await db.execute(
                    select(
                        AnalysisRepoCandidatePage.analysis_job_id,
                        AnalysisRepoCandidatePage.page_no,
                    )
                    .join(AnalysisJob)
                    .where(
                        AnalysisRepoCandidatePage.status == "pending",
                        AnalysisJob.status.in_(("succeeded", "partial")),
                    )
                )
            ).all()
        )
    for run_id, page in pages:
        await enqueue_analysis(ctx["redis"], run_id, page)
