"""report_viewed 이벤트 연결: 200 응답 경로에서만 기록한다. task-17"""

import pytest

from tests.event_helpers import broken_events as broken_events
from tests.event_helpers import fail_commit_on, names

from .factories import make_report
from .test_get import url


async def test_report_viewed_recorded_for_each_200_response(client, db, ctx) -> None:
    interview, _ = ctx
    await make_report(db, interview)
    await db.commit()

    assert (await client.get(url(interview.id))).status_code == 200
    assert (await client.get(url(interview.id))).status_code == 200

    assert await names(db) == ["report_viewed", "report_viewed"]


async def test_report_viewed_not_recorded_for_202_generating(client, db, ctx, enqueue) -> None:
    interview, _ = ctx

    assert (await client.get(url(interview.id))).status_code == 202

    assert await names(db) == []


async def test_report_viewed_failure_does_not_block_200(client, db, ctx, broken_events) -> None:
    interview, _ = ctx
    await make_report(db, interview)
    await db.commit()

    assert (await client.get(url(interview.id))).status_code == 200

    assert await names(db) == []


async def test_report_viewed_commit_failure_still_returns_report(
    client, db, ctx, monkeypatch: pytest.MonkeyPatch
) -> None:
    interview, _ = ctx
    await make_report(db, interview)
    await db.commit()
    fail_commit_on(monkeypatch, nth=1)  # 응답을 만든 뒤의 이벤트 전용 commit

    assert (await client.get(url(interview.id))).status_code == 200

    assert await names(db) == []
