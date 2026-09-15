"""candidate_page_analyze 큐 태스크. pipeline/candidate_page.py 를 호출하는 얇은 껍데기.

docs/pipeline.md Candidate Page / task-11
"""

import uuid
from typing import Any

from app.features.analysis.pipeline.candidate_page import analyze_candidate_page
from app.workers.tasks import worker_session


async def candidate_page_analyze(ctx: dict[str, Any], run_id: str, page: int) -> None:
    """ARQ entrypoint."""
    async with worker_session(ctx) as db:
        await analyze_candidate_page(db, uuid.UUID(run_id), page)
