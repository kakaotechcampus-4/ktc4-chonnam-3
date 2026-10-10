"""Request-scoped sessions; application lifespan owns the engine."""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import HTTPConnection


async def get_db(connection: HTTPConnection) -> AsyncIterator[AsyncSession]:
    async with connection.app.state.session_factory() as session:
        yield session
