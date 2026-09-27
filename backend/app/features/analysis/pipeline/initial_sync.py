"""M1 · job_type='initial_sync'. GitHub 연동 직후 백그라운드, UI 없음.
전체 public 레포의 L0-a(목록 API 응답에 이미 포함된 필드)만 저장. fetch_level='list'.

확정본 §2 M1 / task-08
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.github import Repository
from app.db.models.user import GithubAccount
from app.integrations.github.base import GITHUB_ERROR_TOKEN_INVALID, GithubApiError, RepoSummary
from app.integrations.github.client import GithubClient


async def run_initial_sync(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    github_account_id: uuid.UUID,
    client: GithubClient,
) -> int:
    """전체 public repo L0-a metadata 를 upsert 한다.

    입력: DB session, user_id, github_accounts.id, 토큰이 이미 주입된 GithubClient.
    출력: upsert 한 repo 개수.

    커밋은 호출부(worker task) 가 한다 — service 계층 규칙과 같다(docs/layer-rules.md).
    토큰이 무효(401)면 github_accounts.token_status 를 'revoked' 로 UPDATE 하고
    예외를 그대로 다시 던진다 — ★ client.py 의 401 처리 계약이 여기서 완성된다.
    """
    try:
        repos = await client.list_repositories()
    except GithubApiError as error:
        if error.error_code == GITHUB_ERROR_TOKEN_INVALID:
            await session.execute(
                update(GithubAccount)
                .where(GithubAccount.id == github_account_id)
                .values(token_status="revoked")
            )
        raise

    synced_at = datetime.now(UTC)
    for repo in repos:
        await _upsert_repository(session, user_id=user_id, repo=repo, synced_at=synced_at)
    return len(repos)


async def _upsert_repository(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    repo: RepoSummary,
    synced_at: datetime,
) -> None:
    """L0-a 필드만 upsert. L0-b(languages/readme/head_sha/commit_count) 는 건드리지 않는다 —
    후보로 뽑힌 레포만 repo_detail(task-08 step 3) 에서 채운다.
    """
    values = {
        "user_id": user_id,
        "github_repo_id": repo.github_repo_id,
        "name": repo.name,
        "full_name": repo.full_name,
        "description": repo.description,
        "primary_language": repo.primary_language,
        "topics": repo.topics,
        "stars": repo.stars,
        "forks": repo.forks,
        "size_kb": repo.size_kb,
        "default_branch": repo.default_branch,
        "is_private": repo.is_private,
        "is_fork": repo.is_fork,
        "is_archived": repo.is_archived,
        # list 에 다시 나타났다는 것 자체가 접근 가능하다는 뜻이다.
        "is_accessible": True,
        "pushed_at": repo.pushed_at,
        "synced_at": synced_at,
    }
    stmt = pg_insert(Repository).values(**values)
    update_columns = {
        key: stmt.excluded[key] for key in values if key not in ("user_id", "github_repo_id")
    }
    stmt = stmt.on_conflict_do_update(
        constraint="uq_repositories_user_github_repo",
        set_=update_columns,
    )
    await session.execute(stmt)
