"""이벤트 연결 테스트 공용 helper. task-17"""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.metric import Event


async def names(db: AsyncSession, event_name: str | None = None) -> list[str]:
    """기록된 이벤트 이름을 생성 순으로 돌려준다. 다른 연결에서 커밋된 행도 읽는다."""
    await db.rollback()
    stmt = select(Event.event_name).order_by(Event.created_at, Event.id)
    if event_name is not None:
        stmt = stmt.where(Event.event_name == event_name)
    return list(await db.scalars(stmt))


@pytest.fixture
def broken_events(monkeypatch: pytest.MonkeyPatch) -> None:
    """record_event 의 INSERT 를 CHECK 위반으로 만들어 실패 비차단을 확인한다."""
    import app.shared.events as events

    real = events.Event
    monkeypatch.setattr(events, "Event", lambda **kw: real(**{**kw, "event_name": "not_allowed"}))


def fail_commit_on(monkeypatch: pytest.MonkeyPatch, nth: int) -> None:
    """AsyncSession.commit 의 nth 번째 호출을 DB 오류로 만든다. 이벤트 전용 commit 실패 주입용.

    요청 처리 세션은 테스트의 db 와 다르므로 인스턴스가 아니라 클래스를 바꾼다.
    """
    from sqlalchemy.exc import OperationalError

    real = AsyncSession.commit
    calls = 0

    async def commit(self: AsyncSession) -> None:
        nonlocal calls
        calls += 1
        if calls == nth:
            raise OperationalError("COMMIT", {}, Exception("connection lost"))
        await real(self)

    monkeypatch.setattr(AsyncSession, "commit", commit)
