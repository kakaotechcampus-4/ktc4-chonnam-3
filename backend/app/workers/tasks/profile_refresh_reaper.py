"""보고서 성공 뒤 남은 프로필 전달을 유한 페이지·횟수로 복구한다."""

from typing import Any

from app.features.profile.refresh_outbox import recover


async def profile_refresh_reaper(ctx: dict[str, Any]) -> None:
    await recover(ctx["session_factory"], ctx["redis"])
