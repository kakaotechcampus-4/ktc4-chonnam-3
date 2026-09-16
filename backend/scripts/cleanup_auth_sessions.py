"""만료된 Refresh 세션을 삭제한다. 배포 스케줄러에서 주기적으로 실행한다."""

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
