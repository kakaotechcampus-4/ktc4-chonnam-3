from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import DatabaseSettings
from app.core.errors import AppError


def create_database(
    settings: DatabaseSettings,
) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(settings.database_url, pool_pre_ping=True, hide_parameters=True)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


async def ensure_connection(session: AsyncSession) -> None:
    try:
        await session.connection()
    except (OSError, TimeoutError):
        # asyncpg can raise transport errors before SQLAlchemy wraps a DBAPI error.
        raise AppError("service_unavailable", 503) from None
