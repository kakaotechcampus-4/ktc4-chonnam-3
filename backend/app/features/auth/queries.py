from datetime import datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import CursorResult, delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.user import AuthSession, GitHubAccount, User
from app.db.session import ensure_connection


async def lock_github_identity(session: AsyncSession, github_id: int) -> None:
    # All signup paths lock the provider ID before looking up or creating its user.
    # First login has no row to lock, so concurrent callbacks use an advisory lock.
    await ensure_connection(session)
    await session.execute(
        text("SELECT pg_advisory_xact_lock(:github_id)"), {"github_id": github_id}
    )


async def find_github_account(session: AsyncSession, github_id: int) -> GitHubAccount | None:
    # Existing callbacks must share the row lock used by provider-token refresh.
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
        # After waiting, use the pair committed by the previous lock holder, not an ORM cache.
        .execution_options(populate_existing=True)
    )
    return result.one_or_none()


async def find_user(session: AsyncSession, user_id: UUID) -> User | None:
    await ensure_connection(session)
    return await session.get(User, user_id)


async def lock_user(session: AsyncSession, user_id: UUID) -> User | None:
    # Issuance, refresh, and logout lock the user before touching session rows.
    await ensure_connection(session)
    result = await session.scalars(
        select(User)
        .where(User.id == user_id)
        .with_for_update()
        # Replace any cached ORM value with the generation read under this lock.
        .execution_options(populate_existing=True)
    )
    return result.one_or_none()


async def find_auth_session(session: AsyncSession, sid: UUID) -> AuthSession | None:
    result = await session.scalars(
        select(AuthSession)
        .where(AuthSession.id == sid)
        .with_for_update()
        # An earlier read in this session may still hold the pre-rotation jti.
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
