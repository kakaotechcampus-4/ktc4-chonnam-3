from datetime import datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import CursorResult, delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.user import AuthSession, GitHubAccount, User
from app.db.session import ensure_connection


async def lock_github_identity(session: AsyncSession, github_id: int) -> None:
    # 모든 가입 경로는 사용자 조회·생성 전에 GitHub 사용자 ID로 잠근다.
    # 최초 로그인에는 잠글 행이 없으므로 advisory lock으로 동시 콜백을 직렬화한다.
    await ensure_connection(session)
    await session.execute(
        text("SELECT pg_advisory_xact_lock(:github_id)"), {"github_id": github_id}
    )


async def find_github_account(session: AsyncSession, github_id: int) -> GitHubAccount | None:
    # 기존 계정의 콜백도 GitHub 토큰 갱신과 같은 행 잠금을 사용해야 한다.
    result = await session.scalars(
        select(GitHubAccount)
        .where(GitHubAccount.github_user_id == github_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return result.one_or_none()


async def lock_github_account(session: AsyncSession, user_id: UUID) -> GitHubAccount | None:
    await ensure_connection(session)
    result = await session.scalars(
        select(GitHubAccount)
        .where(GitHubAccount.user_id == user_id)
        .with_for_update()
        # 잠금 대기 후에는 ORM 캐시 대신 앞선 작업이 커밋한 최신 토큰 쌍을 읽는다.
        .execution_options(populate_existing=True)
    )
    return result.one_or_none()


async def find_user(session: AsyncSession, user_id: UUID) -> User | None:
    await ensure_connection(session)
    return await session.get(User, user_id)


async def lock_user(session: AsyncSession, user_id: UUID) -> User | None:
    # 발급·갱신·로그아웃 모두 세션 행에 접근하기 전에 사용자 행부터 잠근다.
    await ensure_connection(session)
    result = await session.scalars(
        select(User)
        .where(User.id == user_id)
        .with_for_update()
        # ORM 캐시를 덮어쓰고 잠금 안에서 읽은 최신 폐기 세대 값을 사용한다.
        .execution_options(populate_existing=True)
    )
    return result.one_or_none()


async def find_auth_session(session: AsyncSession, sid: UUID) -> AuthSession | None:
    result = await session.scalars(
        select(AuthSession)
        .where(AuthSession.id == sid)
        .with_for_update()
        # 같은 DB 세션의 이전 조회 결과에는 갱신 전 jti가 남아 있을 수 있다.
        .execution_options(populate_existing=True)
    )
    return result.one_or_none()


async def delete_auth_session(
    session: AsyncSession, sid: UUID, user_id: UUID, generation: UUID
) -> None:
    await session.execute(
        delete(AuthSession).where(
            AuthSession.id == sid,
            AuthSession.user_id == user_id,
            AuthSession.generation == generation,
        )
    )


async def delete_expired_sessions(session: AsyncSession, now: datetime) -> int:
    await ensure_connection(session)
    result = await session.execute(delete(AuthSession).where(AuthSession.expires_at <= now))
    return cast(CursorResult[Any], result).rowcount
