"""기존 계정·수집·부분 실패 규칙. 실행 claim과 종료 저장은 호출자가 담당한다."""

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.logging import get_logger
from app.db.models.analysis import AnalysisJob
from app.db.models.user import GithubAccount, User
from app.features.analysis.pipeline.steps.repo_analyze import (
    CollectedCandidateBatch,
    collect_candidate_batch,
)
from app.integrations.github.client import GithubClient

logger = get_logger(__name__)


class RunFailure(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def failure_code(error: BaseException) -> str:
    if isinstance(error, AppError):
        return "token_invalid" if error.reason == "github_token_invalid" else error.reason.value
    code = getattr(error, "code", None)
    return code if isinstance(code, str) else "internal_error"


async def account_for_run(ctx: dict[str, Any], user_id: UUID) -> GithubAccount:
    db: AsyncSession
    async with ctx["session_factory"]() as db:
        account = await db.scalar(
            select(GithubAccount)
            .join(User)
            .where(
                GithubAccount.user_id == user_id,
                User.status == "active",
                GithubAccount.token_status == "valid",
            )
        )
        if account is None:
            raise RunFailure("token_invalid")
        db.expunge(account)
        return account


async def collect(ctx: dict[str, Any], run: AnalysisJob, page: int) -> CollectedCandidateBatch:
    account = await account_for_run(ctx, run.user_id)
    client = GithubClient(
        ctx["cipher"].decrypt(account.access_token_encrypted), client=ctx["http_client"]
    )

    async def record_rate_limit(seconds: int) -> None:
        try:
            await ctx["redis"].set(f"gh:rl:{account.github_user_id}", "1", ex=max(1, seconds))
        except Exception:
            logger.warning("github_rate_limit_mirror_lost", run_id=str(run.id))

    return await collect_candidate_batch(
        ctx["session_factory"],
        run.id,
        page,
        github_client=client,
        github_token_encrypted=account.access_token_encrypted,
        login=account.login,
        on_rate_limited=record_rate_limit,
    )


def batch_outcome(snapshots: list[dict[str, object]]) -> tuple[str, str | None]:
    if snapshots and all(s["status"] == "succeeded" for s in snapshots):
        return "succeeded", None
    code = next((str(s["error_code"]) for s in snapshots if s.get("error_code")), "llm_failed")
    if any(s["status"] in {"succeeded", "partial"} for s in snapshots):
        return "partial", code
    return "failed", code
