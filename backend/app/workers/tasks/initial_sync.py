"""initial_sync(repo_sync) 큐 태스크. auth service 가 연동 직후 enqueue 한다.
pipeline/initial_sync.py 를 호출하는 얇은 껍데기.

확정본 §2 M1 / task-08
"""

import uuid
from typing import Any

from app.features.analysis.pipeline.initial_sync import run_initial_sync
from app.workers.tasks import worker_session


async def initial_sync(ctx: dict[str, Any], job_id: str) -> None:
    """ARQ entrypoint. analysis_jobs(job_type='initial_sync') 1건을 처리한다."""
    async with worker_session(ctx) as db:
        await run_initial_sync(db, uuid.UUID(job_id))
