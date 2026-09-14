"""step 3 · L0-b 추가 수집. 후보 레포만 fetch_level='detail' 로 승격.

레포당 3~4회 — languages / readme / commits?per_page=1 / commits?per_page=1&author={login}
head_sha 와 commit_count 를 따로 부르지 않는다: commits?per_page=1 의 body[0].sha 가
head_sha, Link 헤더 rel='last' 의 page=N 이 commit_count 다.

rate limit 이 걸리면 가능한 결과는 저장하고 실패 repo 만 rate_limited 로 기록한다
(run 은 partial 로 끝난다). 401 은 token_invalid 로 run 전체를 멈춘다.

확정본 §2 M2 비용 최적화 / task-08
"""

import uuid

import structlog

from app.core.config import get_settings
from app.core.crypto import decrypt_token
from app.db.models.github import Repository
from app.features.analysis.pipeline.context import RunContext, StepFailed
from app.integrations.github.client import (
    GithubClient,
    GithubError,
    GithubNotFound,
    GithubRateLimited,
    GithubTokenInvalid,
)
from app.shared.clock import now
from app.shared.enums import FetchLevel, JobErrorCode, RepoErrorCode, TokenStatus

logger = structlog.get_logger(__name__)


async def run(ctx: RunContext) -> None:
    """첫 batch 후보를 L0-b 로 승격한다."""
    if not ctx.batch_repository_ids:
        return
    await collect_details(ctx, ctx.batch_repository_ids)


async def collect_details(ctx: RunContext, repository_ids: list[uuid.UUID]) -> None:
    """주어진 repo 들의 languages/README/commit 수를 채운다. page job 도 이 함수를 쓴다."""
    account = ctx.github_account
    if account is None or account.token_status != TokenStatus.VALID:
        raise StepFailed(JobErrorCode.TOKEN_INVALID)

    settings = get_settings()
    token = decrypt_token(account.access_token_encrypted)
    async with GithubClient(token) as client:
        for repository_id in repository_ids:
            repo = await ctx.db.get(Repository, repository_id)
            if repo is None:  # pragma: no cover - 후보 생성 직후 삭제된 경우
                continue
            try:
                await _fetch_one(client, repo, account.login, settings.readme_max_chars)
            except GithubTokenInvalid:
                account.token_status = str(TokenStatus.REVOKED)
                await ctx.db.commit()
                raise StepFailed(JobErrorCode.TOKEN_INVALID) from None
            except GithubRateLimited:
                _mark_failed(repo, RepoErrorCode.RATE_LIMITED)
                ctx.failed_repository_ids[repo.id] = str(RepoErrorCode.RATE_LIMITED)
                logger.warning("repo_detail_rate_limited", repo=repo.full_name)
            except GithubNotFound:
                _mark_failed(repo, RepoErrorCode.REPO_UNREACHABLE)
                ctx.failed_repository_ids[repo.id] = str(RepoErrorCode.REPO_UNREACHABLE)
            except GithubError as exc:
                _mark_failed(repo, RepoErrorCode.REPO_UNREACHABLE)
                ctx.failed_repository_ids[repo.id] = str(RepoErrorCode.REPO_UNREACHABLE)
                logger.warning("repo_detail_failed", repo=repo.full_name, error=str(exc))
            await ctx.db.commit()

    logger.info(
        "repo_detail_done",
        run_id=str(ctx.job.id),
        requested=len(repository_ids),
        failed=len(ctx.failed_repository_ids),
    )


async def _fetch_one(
    client: GithubClient, repo: Repository, login: str, readme_max_chars: int
) -> None:
    repo.languages = await client.get_languages(repo.full_name)
    readme = await client.get_readme(repo.full_name)
    if readme is None:
        repo.readme_text = None
        repo.readme_truncated = False
    else:
        repo.readme_text = readme[:readme_max_chars]
        repo.readme_truncated = len(readme) > readme_max_chars
    head = await client.get_head_commit_info(repo.full_name)
    repo.head_sha = head.head_sha
    repo.commit_count = head.commit_count
    repo.user_commit_count = await client.get_author_commit_count(repo.full_name, login)
    repo.fetch_level = str(FetchLevel.DETAIL)
    repo.fetch_error_code = None
    repo.detail_fetched_at = now()


def _mark_failed(repo: Repository, error_code: RepoErrorCode) -> None:
    """가능한 결과는 남기고 실패 사유만 표시한다."""
    repo.fetch_error_code = str(error_code)
    repo.detail_fetched_at = now()
