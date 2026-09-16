from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.user import GitHubAccount


async def has_valid_github_account(session: AsyncSession, user_id: UUID) -> bool:
    # An expired access token is still refreshable; /me checks metadata without calling GitHub.
    return (
        await session.scalar(
            select(GitHubAccount.id).where(
                GitHubAccount.user_id == user_id,
                GitHubAccount.token_status == "valid",
                or_(
                    GitHubAccount.token_expires_at.is_(None),
                    GitHubAccount.token_expires_at > func.now(),
                    GitHubAccount.refresh_token_expires_at > func.now(),
                ),
            )
        )
        is not None
    )
