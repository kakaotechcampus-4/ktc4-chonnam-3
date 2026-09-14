"""analysis_run 큐 태스크. pipeline/analysis_run.py 를 호출하는 얇은 껍데기.

재시도 시 API 에서도 같은 pipeline 을 호출하므로 로직을 여기 쓰지 않는다.

docs/layer-rules.md 1절 / task-11
"""

import uuid
from typing import Any

from app.features.analysis.pipeline.analysis_run import run_analysis
from app.workers.tasks import worker_session


async def analysis_run(ctx: dict[str, Any], run_id: str) -> None:
    """ARQ entrypoint."""
    async with worker_session(ctx) as db:
        await run_analysis(db, uuid.UUID(run_id))
