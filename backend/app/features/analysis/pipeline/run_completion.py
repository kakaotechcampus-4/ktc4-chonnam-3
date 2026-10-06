"""분석과 페이지를 함께 종료하고 실행 지표를 저장한다."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select

from app.db.models.analysis import AnalysisJob, AnalysisRepoCandidatePage
from app.features.analysis.pipeline.run_state import elapsed, notify


async def finish_page(ctx: dict[str, Any], run_id: UUID, page: int, error: str | None) -> None:
    async with ctx["session_factory"].begin() as db:
        row = await db.scalar(
            select(AnalysisRepoCandidatePage)
            .where(
                AnalysisRepoCandidatePage.analysis_job_id == run_id,
                AnalysisRepoCandidatePage.page_no == page,
            )
            .with_for_update()
        )
        if row is None or row.status not in {"pending", "running"}:
            return
        complete_page(row, error)


def complete_page(row: AnalysisRepoCandidatePage, error: str | None) -> None:
    row.status = "failed" if error else "succeeded"
    row.error_code = error
    row.completed_at = datetime.now(UTC)
    row.duration_ms = elapsed(row.started_at, row.completed_at)
    row.queue_wait_ms = elapsed(row.requested_at, row.started_at) if row.started_at else None


async def finish_run(ctx: dict[str, Any], run_id: UUID, status: str, error: str | None) -> None:
    async with ctx["session_factory"].begin() as db:
        run = await db.scalar(select(AnalysisJob).where(AnalysisJob.id == run_id).with_for_update())
        if run is None or run.status != "running":
            return
        run.status, run.error_code = status, error
        run.completed_at = datetime.now(UTC)
        run.duration_ms = elapsed(run.started_at, run.completed_at)
        # 중단 시 실행 중인 단계와 아직 실행하지 않은 단계를 구분해 남긴다.
        run.steps = [
            {**s, "status": "failed" if s["status"] == "running" else "skipped"}
            if s["status"] in {"running", "pending"}
            else s
            for s in run.steps
        ]
        # run 완료를 조회한 순간 page 1도 완료 상태여야 한다.
        page = await db.scalar(
            select(AnalysisRepoCandidatePage)
            .where(
                AnalysisRepoCandidatePage.analysis_job_id == run_id,
                AnalysisRepoCandidatePage.page_no == 1,
            )
            .with_for_update()
        )
        if page is not None and page.status in {"pending", "running"}:
            complete_page(page, error if status == "failed" else None)
        states = {str(item["key"]): str(item["status"]) for item in run.steps}
    await notify(
        ctx,
        run_id,
        {"type": "completed"}
        if status == "succeeded"
        else {"type": "failed", "reason": error or "internal_error"},
        states,
    )
