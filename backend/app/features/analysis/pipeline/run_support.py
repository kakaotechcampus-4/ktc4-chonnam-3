"""기존 계정·수집·부분 실패 규칙. 실행 claim과 종료 저장은 호출자가 담당한다."""

import traceback
from pathlib import PurePath
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
from app.integrations.jd.base import PostingFetchError
from app.llm_tasks.jd_extract import JdExtractionError

logger = get_logger(__name__)


class RunFailure(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


# 코드로 분류되는 예상 업무 실패. `.code` 속성 유무로 가르지 않는 이유: SQLAlchemy 예외도
# `.code`("f405" 등)를 갖고 있어 DB 오류가 예상 실패로 분류된다.
EXPECTED_FAILURES = (RunFailure, AppError, PostingFetchError, JdExtractionError)
_MAX_CHAIN, _MAX_FRAMES = 4, 5


def unexpected_failure_fields(error: BaseException) -> dict[str, Any]:
    """예상 밖 예외의 진단 필드. 예상 실패는 코드만 남기므로 빈 dict.

    예외 타입과 호출 위치(파일·함수·줄번호)만 남긴다. 예외 메시지·인자·locals 는 SQL 값,
    문서 본문 같은 업무 내용을 담을 수 있어 Console·JSON 어느 출력에도 넣지 않는다.
    """
    if isinstance(error, EXPECTED_FAILURES):
        return {}
    chain: list[dict[str, Any]] = []
    current: BaseException | None = error
    while current is not None and len(chain) < _MAX_CHAIN:
        frames = traceback.extract_tb(current.__traceback__)[-_MAX_FRAMES:]
        chain.append(
            {
                "type": f"{type(current).__module__}.{type(current).__qualname__}",
                "frames": [
                    f"{'/'.join(PurePath(f.filename).parts[-3:])}:{f.name}:{f.lineno}"
                    for f in frames
                ],
            }
        )
        current = current.__cause__ or current.__context__
    return {"error_chain": chain}


def failure_code(error: BaseException) -> str:
    if isinstance(error, AppError):
        return "token_invalid" if error.reason == "github_token_invalid" else error.reason.value
    code = getattr(error, "code", None)
    return (
        code if isinstance(error, EXPECTED_FAILURES) and isinstance(code, str) else "internal_error"
    )


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
