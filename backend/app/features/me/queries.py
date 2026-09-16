from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.user import GitHubAccount


async def has_valid_github_account(session: AsyncSession, user_id: UUID) -> bool:
    return (
        await session.scalar(
            select(GitHubAccount.id).where(
                GitHubAccount.user_id == user_id, GitHubAccount.token_status == "valid"
            )
        )
        is not None
    )
