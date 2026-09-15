from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.models.user import User
from app.features.auth import service


def get_settings(request: Request) -> Settings:
    return request.app.state.settings  # type: ignore[no-any-return]


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.sessions() as session:
        yield session


DbSession = Annotated[AsyncSession, Depends(get_session)]


async def current_user(request: Request, session: DbSession) -> User:
    return await service.authenticate(
        session, request.app.state.tokens, request.cookies.get("accessToken")
    )


CurrentUser = Annotated[User, Depends(current_user)]
