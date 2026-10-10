"""Identity reads and writes. The authentication service owns the transaction."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.user import GithubAccount, User


async def github_identity(
    db: AsyncSession, github_user_id: int
) -> tuple[User, GithubAccount] | None:
    row = (
        await db.execute(
            select(User, GithubAccount)
            .join(GithubAccount, GithubAccount.user_id == User.id)
            .where(GithubAccount.github_user_id == github_user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).one_or_none()
    return (row[0], row[1]) if row is not None else None


async def user_identity(db: AsyncSession, user_id: UUID) -> tuple[User, GithubAccount] | None:
    # OAuth 외부 호출 중 바뀐 계정 상태를 반영하도록 세션에 이미 로드된 객체도 다시 읽는다.
    row = (
        await db.execute(
            select(User, GithubAccount)
            .join(GithubAccount, GithubAccount.user_id == User.id)
            .where(User.id == user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).one_or_none()
    return (row[0], row[1]) if row is not None else None


async def add_identity(db: AsyncSession, user: User, account: GithubAccount) -> None:
    db.add(user)
    await db.flush()
    account.user_id = user.id
    db.add(account)
    await db.flush()
