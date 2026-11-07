"""analysis_run_completed / analysis_run_failed 이벤트 연결. task-17"""

from datetime import UTC, datetime
from uuid import UUID

import pytest

from app.db.models.analysis import AnalysisJob
from app.features.analysis.pipeline.run_completion import finish_run
from tests.event_helpers import broken_events as broken_events
from tests.event_helpers import names
from tests.features.test_analysis_api import member as member

POSTING = {"postingUrl": "https://wanted.co.kr/wd/1"}


def _context(app):
    return {
        "session_factory": app.state.session_factory,
        "redis": app.state.redis,
        "settings": app.state.settings,
    }


async def _running(client, db) -> UUID:
    response = await client.post("/api/analysis-runs", json=POSTING)
    assert response.status_code == 202
    run = await db.get(AnalysisJob, UUID(response.json()["runId"]))
    run.status, run.started_at = "running", datetime.now(UTC)
    await db.commit()
    return run.id


@pytest.mark.parametrize(
    ("status", "error", "expected"),
    [
        ("succeeded", None, "analysis_run_completed"),
        ("partial", "repo_analysis_failed", "analysis_run_failed"),
        ("failed", "internal_error", "analysis_run_failed"),
    ],
)
async def test_run_finish_recorded_once_even_when_finished_twice(
    app, client, member, db, status, error, expected
):
    run_id = await _running(client, db)

    await finish_run(_context(app), run_id, status, error)
    await finish_run(_context(app), run_id, status, error)

    assert await names(db, expected) == [expected]
    assert len(await names(db)) == 2  # started + 종료 1건


async def test_run_finish_failure_does_not_block_termination(
    app, client, member, db, broken_events
):
    run_id = await _running(client, db)

    await finish_run(_context(app), run_id, "succeeded", None)

    await db.rollback()
    assert (await db.get(AnalysisJob, run_id)).status == "succeeded"
