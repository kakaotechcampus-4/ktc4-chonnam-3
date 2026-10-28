"""ARQ에는 분석 ID만 전달하고 인증 자료는 실행 시 DB에서 읽는다."""

from typing import Any
from uuid import UUID

from app.features.analysis.pipeline.run import run_analysis


async def analysis_run(ctx: dict[str, Any], run_id: str) -> None:
    await run_analysis(ctx, UUID(run_id))
