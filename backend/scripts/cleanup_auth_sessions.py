"""Delete expired refresh sessions; invoke periodically from the deployment scheduler."""

import asyncio
import sys

from app.core.config import DatabaseSettings
from app.db.session import create_database
from app.features.auth.service import cleanup_expired_sessions


async def main() -> None:
    engine, sessions = create_database(DatabaseSettings())
    try:
        async with sessions() as session:
            deleted = await cleanup_expired_sessions(session)
        print(f"Deleted {deleted} expired auth session(s).")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:
        print("Auth session cleanup failed.", file=sys.stderr)
        sys.exit(1)
