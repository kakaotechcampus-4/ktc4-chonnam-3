"""ARQ adapter. Job arguments contain only the persisted job identifier."""

from typing import Any
from uuid import UUID

from app.features.analysis.pipeline.initial_sync import run_initial_sync


async def initial_sync(ctx: dict[str, Any], analysis_job_id: str) -> None:
    async with ctx["session_factory"]() as db:
        await run_initial_sync(db, UUID(analysis_job_id), ctx["http_client"], ctx["cipher"])
