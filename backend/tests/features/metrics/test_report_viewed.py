"""report_viewed 이벤트 count 쿼리.

task-17
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Event
from app.features.metrics import queries


async def test_counts_only_report_viewed(db: AsyncSession) -> None:
    db.add_all(
        [
            Event(event_name="report_viewed"),
            Event(event_name="report_viewed"),
            Event(event_name="interview_completed"),
        ]
    )
    await db.flush()

    assert await queries.count_report_viewed(db) == 2


async def test_zero_without_events(db: AsyncSession) -> None:
    assert await queries.count_report_viewed(db) == 0


async def test_period_filter(db: AsyncSession) -> None:
    now = datetime.now(UTC)
    db.add_all(
        [
            Event(event_name="report_viewed", created_at=now - timedelta(days=10)),
            Event(event_name="report_viewed", created_at=now),
        ]
    )
    await db.flush()

    since = now - timedelta(days=1)
    assert await queries.count_report_viewed(db, since=since) == 1
    assert await queries.count_report_viewed(db, until=since) == 1
