from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.user import User
from app.features.me.queries import has_valid_github_account
from app.features.me.schemas import MeResponse


async def identity(session: AsyncSession, user: User) -> MeResponse:
    return MeResponse(
        name=user.display_name,
        avatar_url=user.avatar_url,
        github_linked=await has_valid_github_account(session, user.id),
    )
