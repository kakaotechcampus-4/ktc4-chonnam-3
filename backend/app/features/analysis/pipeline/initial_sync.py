"""Persist and enqueue public metadata synchronization after OAuth commits."""

import asyncio
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

import httpx
from arq.connections import ArqRedis
from arq.jobs import Job, JobStatus
from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import TokenCipher
from app.core.errors import AppError, Reason
from app.db.models.analysis import AnalysisJob
from app.db.models.github import Repository
from app.db.models.user import GithubAccount, User
from app.integrations.github.base import GithubApiError
from app.integrations.github.client import GithubClient


async def enqueue_initial_sync(db: AsyncSession, redis: ArqRedis, user_id: UUID) -> UUID | None:
    """Create one active job per user, committing before the worker can observe it."""
    job_id = await db.scalar(
        insert(AnalysisJob)
        .values(
            id=uuid4(),
            user_id=user_id,
            job_type="initial_sync",
            status="queued",
            queued_at=datetime.now(UTC),
        )
        .on_conflict_do_nothing(
            index_elements=["user_id", "job_type"],
            index_where=text("status IN ('queued', 'running')"),
        )
        .returning(AnalysisJob.id)
    )
    if job_id is None:
        existing = (
            await db.execute(
                select(AnalysisJob.id, AnalysisJob.status).where(
                    AnalysisJob.user_id == user_id,
                    AnalysisJob.job_type == "initial_sync",
                    AnalysisJob.status.in_(("queued", "running")),
                )
            )
        ).one_or_none()
        if existing is None:
            # INSERT와 SELECT 사이에 기존 작업이 끝났으므로 새 작업 생성을 다시 시도한다.
            await db.commit()
            return await enqueue_initial_sync(db, redis, user_id)
        job_id, status = cast(UUID, existing[0]), existing[1]
        if status == "running":
            # Redis 키 유실만으로 워커 중단을 단정할 수 없어 실행 중인 작업을 중복 생성하지 않는다.
            # 워커 유실을 운영자가 확인하고 DB 작업을 종료한 뒤에만 새 실행을 허용한다.
            await db.commit()
            return job_id
    # 워커가 큐를 읽기 전에 DB 작업을 확정하고 Redis에는 토큰 없이 작업 ID만 전달한다.
    await db.commit()
    try:
        queued = await redis.enqueue_job(
            "initial_sync", str(job_id), _job_id=f"initial_sync:{job_id}"
        )
        if queued is None and await Job(f"initial_sync:{job_id}", redis).status() in {
            JobStatus.not_found,
            JobStatus.complete,
        }:
            # ARQ가 함수 진입 전에 종료되거나 큐에서 빠진 payload만 남아 있을 수 있다.
            # DB도 완료됐으면 정상이며 실행할 수 없는 queued 작업은 실패 처리해 재시도를 허용한다.
            status = await db.scalar(select(AnalysisJob.status).where(AnalysisJob.id == job_id))
            if status == "queued":
                raise RuntimeError("Queued database job has no runnable ARQ job")
    except Exception:
        await db.execute(
            update(AnalysisJob)
            .where(AnalysisJob.id == job_id, AnalysisJob.status == "queued")
            .values(
                status="failed",
                error_code="internal_error",
                completed_at=datetime.now(UTC),
            )
        )
        await db.commit()
        raise AppError(Reason.INTERNAL_ERROR) from None
    return job_id


async def run_initial_sync(
    db: AsyncSession,
    job_id: UUID,
    http: httpx.AsyncClient,
    cipher: TokenCipher,
) -> None:
    """Collect public repositories; DB records describe success and every failure."""
    started_at = datetime.now(UTC)
    user_id = await db.scalar(
        update(AnalysisJob)
        .where(
            AnalysisJob.id == job_id,
            AnalysisJob.job_type == "initial_sync",
            AnalysisJob.status == "queued",
        )
        .values(status="running", started_at=started_at)
        .returning(AnalysisJob.user_id)
    )
    await db.commit()
    if user_id is None:
        return
    account_id: UUID | None = None
    token_snapshot: bytes | None = None
    try:
        account = await db.scalar(
            select(GithubAccount)
            .join(User, User.id == GithubAccount.user_id)
            .where(GithubAccount.user_id == user_id, User.status == "active")
        )
        if account is None or account.token_status != "valid":
            raise GithubApiError("token_invalid")
        account_id, token_snapshot = account.id, account.access_token_encrypted
        token = cipher.decrypt(token_snapshot)
        await db.commit()
        for attempt in range(2):
            try:
                repositories = await GithubClient(token, client=http).list_repositories()
                break
            except GithubApiError as error:
                if attempt or error.error_code != "token_invalid":
                    raise
                replacement = (
                    await db.execute(
                        select(GithubAccount.id, GithubAccount.access_token_encrypted)
                        .join(User, User.id == GithubAccount.user_id)
                        .where(
                            GithubAccount.user_id == user_id,
                            GithubAccount.token_status == "valid",
                            User.status == "active",
                        )
                    )
                ).one_or_none()
                await db.commit()
                if replacement is None or replacement[1] == token_snapshot:
                    raise
                # 재연동도 실행 중인 이 작업을 재사용하므로 교체된 토큰으로 한 번 더 시도한다.
                # 이전 토큰의 늦은 401 응답 때문에 재연동 후 수집까지 실패하지 않게 한다.
                account_id, token_snapshot = replacement
                token = cipher.decrypt(token_snapshot)
        synced_at = datetime.now(UTC)
        ids = [repo.github_repo_id for repo in repositories]
        # 전체 목록 수집에 성공한 경우에만 누락·비공개 저장소를 접근 불가로 바꾼다.
        await db.execute(
            update(Repository)
            .where(
                Repository.user_id == user_id,
                Repository.github_repo_id.not_in(ids),
            )
            .values(is_accessible=False)
        )
        for repo in repositories:
            values = repo.model_dump()
            values.update(user_id=user_id, is_accessible=True, synced_at=synced_at)
            await db.execute(
                insert(Repository)
                .values(**values)
                .on_conflict_do_update(
                    constraint="uq_repositories_user_github_repo",
                    set_=values,
                )
            )
        await db.execute(
            update(GithubAccount)
            .where(
                GithubAccount.id == account_id,
                GithubAccount.access_token_encrypted == token_snapshot,
            )
            .values(public_repo_count=len(ids))
        )
        await db.execute(
            update(AnalysisJob)
            .where(AnalysisJob.id == job_id)
            .values(
                status="succeeded",
                error_code=None,
                completed_at=synced_at,
                duration_ms=int((synced_at - started_at).total_seconds() * 1000),
            )
        )
        await db.commit()
    except (Exception, asyncio.CancelledError) as exc:
        await db.rollback()
        error_code = exc.error_code if isinstance(exc, GithubApiError) else "internal_error"
        if error_code == "token_invalid" and account_id is not None and token_snapshot is not None:
            # 요청에 사용한 토큰이 여전히 저장돼 있을 때만 무효화해 새 연동 토큰을 보호한다.
            await db.execute(
                update(GithubAccount)
                .where(
                    GithubAccount.id == account_id,
                    GithubAccount.access_token_encrypted == token_snapshot,
                )
                .values(token_status="revoked")
            )
        await db.execute(
            update(AnalysisJob)
            .where(AnalysisJob.id == job_id)
            .values(
                status="failed",
                error_code=error_code,
                completed_at=datetime.now(UTC),
            )
        )
        await db.commit()
        if isinstance(exc, asyncio.CancelledError):
            raise
