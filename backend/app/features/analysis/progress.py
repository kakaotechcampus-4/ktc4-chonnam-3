"""run 진행 상태 갱신 — Postgres -> Redis mirror -> Pub/Sub publish 순서를 강제한다.

SSE 가 먼저 완료를 받고 DB 가 아직 running 인 상태를 막기 위해 이 순서를 지킨다
(docs/pipeline.md 2절). SSE 소비자는 task-12 에서 붙는다.
"""

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.analysis import AnalysisJob
from app.realtime.bus import mirror_run_steps, publish_run_event
from app.shared.clock import now
from app.shared.enums import STEP_ORDER, JobStatus, StepKey, StepStatus

logger = structlog.get_logger(__name__)

#: running step 은 절반만 반영한다 (FE 진행률이 멈춰 보이지 않도록).
_RUNNING_WEIGHT = 0.5


def initial_steps() -> dict[str, str]:
    """7 step 을 모두 pending 으로 둔 초기값."""
    return {str(key): str(StepStatus.PENDING) for key in STEP_ORDER}


def compute_progress(steps: dict[str, str]) -> int:
    """완료 step 수 기반 0~100. 종료(succeeded/failed) step 은 가중치 1."""
    if not steps:
        return 0
    unit = 100 / len(STEP_ORDER)
    total = 0.0
    for key in STEP_ORDER:
        status = steps.get(str(key), str(StepStatus.PENDING))
        if status in (StepStatus.SUCCEEDED, StepStatus.FAILED):
            total += unit
        elif status == StepStatus.RUNNING:
            total += unit * _RUNNING_WEIGHT
    return min(100, round(total))


async def _sync_mirror(job: AnalysisJob, event: dict[str, object]) -> None:
    """Redis mirror 와 publish. Redis 장애가 run 을 죽이지 않게 감싼다."""
    run_id = str(job.id)
    payload = {**job.steps, "__status": job.status, "__progress": str(job.progress)}
    try:
        await mirror_run_steps(run_id, payload)
        await publish_run_event(run_id, event)
    except Exception as exc:  # noqa: BLE001 - Redis 는 영구 원본이 아니다
        logger.warning("run_progress_mirror_failed", run_id=run_id, error=str(exc))


async def mark_step(db: AsyncSession, job: AnalysisJob, key: StepKey, status: StepStatus) -> None:
    """step 1개 상태를 바꾸고 progress 를 다시 계산한다."""
    steps = dict(job.steps or initial_steps())
    steps[str(key)] = str(status)
    job.steps = steps
    job.progress = compute_progress(steps)
    if job.status == JobStatus.QUEUED:
        job.status = str(JobStatus.RUNNING)
        job.started_at = job.started_at or now()
    await db.commit()
    await _sync_mirror(job, {"type": "step", "key": str(key), "status": str(status)})
    await _sync_mirror(job, {"type": "progress", "value": job.progress})


async def finish_run(
    db: AsyncSession,
    job: AnalysisJob,
    status: JobStatus,
    *,
    error_code: str | None = None,
) -> None:
    """run 종료. partial/failed 는 FE 에서 모두 failed 로 보인다."""
    job.status = str(status)
    job.error_code = error_code
    job.finished_at = now()
    if status == JobStatus.SUCCEEDED:
        job.progress = 100
    await db.commit()
    event: dict[str, object] = (
        {"type": "completed"}
        if status == JobStatus.SUCCEEDED
        else {"type": "failed", "reason": error_code or str(status)}
    )
    await _sync_mirror(job, event)
