from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.user import GitHubAccount


async def has_valid_github_account(session: AsyncSession, user_id: UUID) -> bool:
    # GitHub Access가 만료돼도 갱신 가능하면 연결은 유지되며, /me는 GitHub 호출 없이 판단한다.
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
