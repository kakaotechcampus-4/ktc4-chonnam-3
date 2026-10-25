"""면접 식별자를 검증하고 같은 준비 실행 경로를 호출하는 ARQ 어댑터."""

from typing import Any
from uuid import UUID

from app.core.config import get_settings
from app.db.models import InterviewSession
from app.features.interview.prepare import prepare_interview


async def interview_prep(ctx: dict[str, Any], interview_id: str) -> None:
    key = UUID(interview_id)
    async with ctx["session_factory"]() as db:
        row = await db.get(InterviewSession, key)
        if row is None or row.status != "preparing":
            return
        user_id = row.user_id
    await prepare_interview(
        ctx["session_factory"],
        user_id=user_id,
        interview_id=key,
        settings=ctx.get("settings") or get_settings(),
        http_client=ctx["http_client"],
    )
