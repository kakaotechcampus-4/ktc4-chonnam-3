"""FE가 실제 받는 SSE 형식과 DB 복원 경로를 검증한다."""

import json
from uuid import UUID

from app.db.models.analysis import AnalysisJob
from tests.features.test_analysis_api import member as member


async def test_terminal_sse_uses_data_type_key_and_restores_failure(client, member, db):
    created = await client.post(
        "/api/analysis-runs", json={"postingUrl": "https://wanted.co.kr/wd/1"}
    )
    run = await db.get(AnalysisJob, UUID(created.json()["runId"]))
    run.status, run.error_code = "failed", "jd_fetch_failed"
    run.steps = [
        {**s, "status": "failed" if s["key"] == "jd_fetch" else "skipped"} for s in run.steps
    ]
    await db.commit()
    response = await client.get(f"/api/analysis-runs/{run.id}/events")
    assert response.status_code == 200
    assert response.headers["x-accel-buffering"] == "no"
    assert "event:" not in response.text
    values = [
        json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")
    ]
    assert values[-1] == {"type": "failed", "reason": "jd_fetch_failed"}
    steps = [v for v in values if v["type"] == "step"]
    assert len(steps) == 7 and all("key" in v and "step" not in v for v in steps)
    assert any(v["type"] == "progress" for v in values)
