"""후보 페이지 작업은 원래 run의 완료 상태를 바꾸지 않는다."""

from typing import Any
from uuid import UUID

from app.features.analysis.pipeline.run import run_candidate_page


async def candidate_page_analyze(ctx: dict[str, Any], run_id: str, page: int) -> None:
    await run_candidate_page(ctx, UUID(run_id), page)
