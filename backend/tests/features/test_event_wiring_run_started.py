"""analysis_run_started 이벤트 연결. task-17"""

from tests.event_helpers import broken_events as broken_events
from tests.event_helpers import names
from tests.features.test_analysis_api import member as member

POSTING = {"postingUrl": "https://wanted.co.kr/wd/1"}


async def test_run_started_recorded_once_and_not_for_duplicate_request(client, member, db):
    assert (await client.post("/api/analysis-runs", json=POSTING)).status_code == 202
    assert (await client.post("/api/analysis-runs", json=POSTING)).status_code == 409

    assert await names(db) == ["analysis_run_started"]


async def test_run_started_failure_does_not_block_run_creation(client, member, db, broken_events):
    assert (await client.post("/api/analysis-runs", json=POSTING)).status_code == 202

    await db.rollback()
    assert await names(db) == []
