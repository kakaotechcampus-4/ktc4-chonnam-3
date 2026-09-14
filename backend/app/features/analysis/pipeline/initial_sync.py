"""initial_sync (repo_sync) · GitHub 연동 직후 백그라운드, UI 없음.

전체 public 레포의 L0-a(목록 API 응답에 이미 포함된 필드)만 저장한다. fetch_level='list'.
private repo 는 조회 자체를 하지 않는다 (visibility=public). L0-b 는 repo_detail step 이다.

rate limit 은 수집한 만큼 저장하고 job 을 partial 로 끝낸다. 401 은 token_status 를
revoked 로 내리고 token_invalid 로 끝낸다.

확정본 §2 M1 / task-08
"""

import uuid
from datetime import datetime
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt_token
from app.db.models.analysis import AnalysisJob
from app.db.models.github import Repository
from app.db.models.user import GithubAccount
from app.integrations.github.client import (
    GithubClient,
    GithubError,
    GithubRateLimited,
    GithubTokenInvalid,
)
from app.shared.clock import now
from app.shared.enums import FetchLevel, JobErrorCode, JobStatus, JobType, TokenStatus

logger = structlog.get_logger(__name__)


async def sync_user_repositories(db: AsyncSession, user_id: uuid.UUID) -> int:
    """사용자의 public repo 목록을 upsert 한다. 저장한 repo 수를 돌려준다."""
    account = (
        await db.execute(select(GithubAccount).where(GithubAccount.user_id == user_id))
    ).scalar_one_or_none()
    if account is None or account.token_status != TokenStatus.VALID:
        raise GithubTokenInvalid("github account is not connected")

    token = decrypt_token(account.access_token_encrypted)
    async with GithubClient(token) as client:
        try:
            payloads = await client.list_public_repos()
        except GithubTokenInvalid:
            account.token_status = str(TokenStatus.REVOKED)
            await db.commit()
            raise

    existing = {
        repo.github_repo_id: repo
        for repo in (
            await db.execute(select(Repository).where(Repository.user_id == user_id))
        ).scalars()
    }
    for payload in payloads:
        _upsert(db, user_id, existing, payload)
    account.synced_at = now()
    await db.commit()
    logger.info("initial_sync_done", user_id=str(user_id), repos=len(payloads))
    return len(payloads)


async def run_initial_sync(db: AsyncSession, job_id: uuid.UUID) -> None:
    """analysis_jobs(job_type='initial_sync') 한 건을 실행한다."""
    job = await db.get(AnalysisJob, job_id)
    if job is None or job.job_type != JobType.INITIAL_SYNC:
        logger.warning("initial_sync_job_missing", job_id=str(job_id))
        return
    job.status = str(JobStatus.RUNNING)
    job.started_at = now()
    await db.commit()

    try:
        count = await sync_user_repositories(db, job.user_id)
    except GithubTokenInvalid:
        await _finish(db, job, JobStatus.FAILED, JobErrorCode.TOKEN_INVALID)
        return
    except GithubRateLimited:
        await _finish(db, job, JobStatus.PARTIAL, JobErrorCode.RATE_LIMITED)
        return
    except GithubError as exc:
        logger.warning("initial_sync_failed", job_id=str(job_id), error=str(exc))
        await _finish(db, job, JobStatus.FAILED, None)
        return

    if count == 0:
        await _finish(db, job, JobStatus.FAILED, JobErrorCode.NO_PUBLIC_REPO)
        return
    await _finish(db, job, JobStatus.SUCCEEDED, None)


async def _finish(
    db: AsyncSession, job: AnalysisJob, status: JobStatus, error_code: JobErrorCode | None
) -> None:
    job.status = str(status)
    job.error_code = str(error_code) if error_code else None
    job.progress = 100 if status == JobStatus.SUCCEEDED else job.progress
    job.finished_at = now()
    await db.commit()


def _upsert(
    db: AsyncSession,
    user_id: uuid.UUID,
    existing: dict[int, Repository],
    payload: dict[str, Any],
) -> None:
    """목록 응답 필드만 반영한다. L0-b 필드는 건드리지 않는다."""
    github_repo_id = int(payload["id"])
    repo = existing.get(github_repo_id)
    if repo is None:
        repo = Repository(user_id=user_id, github_repo_id=github_repo_id)
        db.add(repo)
        existing[github_repo_id] = repo
    repo.full_name = str(payload["full_name"])
    repo.name = str(payload["name"])
    repo.description = payload.get("description")
    repo.html_url = str(payload.get("html_url") or f"https://github.com/{repo.full_name}")
    repo.default_branch = payload.get("default_branch")
    repo.primary_language = payload.get("language")
    repo.topics = list(payload.get("topics") or [])
    repo.stars = int(payload.get("stargazers_count") or 0)
    repo.forks = int(payload.get("forks_count") or 0)
    repo.size_kb = int(payload.get("size") or 0)
    repo.is_private = bool(payload.get("private"))
    repo.is_fork = bool(payload.get("fork"))
    repo.is_archived = bool(payload.get("archived"))
    repo.repo_created_at = _parse_dt(payload.get("created_at"))
    repo.repo_pushed_at = _parse_dt(payload.get("pushed_at"))
    repo.synced_at = now()
    if not repo.fetch_level:
        repo.fetch_level = str(FetchLevel.LIST)


def _parse_dt(value: Any) -> datetime | None:
    """GitHub ISO8601(Z) -> aware datetime."""
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:  # pragma: no cover - GitHub 형식이 바뀐 경우
        return None
