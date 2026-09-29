"""GitHub 제한부터 실제 ARQ·Redis·DB 결과와 SSE 응답까지 연결한다."""

import asyncio
import json
import math
import time
from uuid import UUID

import httpx
import pytest
from sqlalchemy import select

from app.db.models.analysis import AnalysisJob, AnalysisRepoCandidate
from app.realtime.bus import RedisEventBus
from tests.features.test_analysis_api import member as member
from tests.features.test_analysis_worker import (
    _drain,
    _http_handler,
    _start,
)
from tests.features.test_analysis_worker import app_settings as app_settings
from tests.features.test_analysis_worker import repositories as repositories


@pytest.mark.parametrize("status_code", [429, 403])
@pytest.mark.parametrize("successful_count,run_status", [(1, "partial"), (0, "failed")])
async def test_github_limit_preserves_results_and_records_run_ttl_and_events(
    client, db, app, repositories, status_code, successful_count, run_status
):
    # 제한 이후 호출을 계속하거나 callback·실패 snapshot·종료 알림을 빠뜨리면 실패한다.
    run_id = await _start(client)
    normal_handler, requests = _http_handler()
    github_paths: list[str] = []
    limited_at: float | None = None
    blocked_path = f"/repos/analysis-user/repo{successful_count}/languages"

    def handler(request):
        nonlocal limited_at
        if request.url.host == "api.github.com":
            github_paths.append(request.url.path)
            if request.url.path == blocked_path:
                limited_at = time.monotonic()
                return httpx.Response(
                    status_code,
                    headers={"Retry-After": "90"},
                    json={"message": "You have exceeded a secondary rate limit"},
                )
        return normal_handler(request)

    # 실제 구독을 먼저 성립시켜 워커가 발행한 payload를 DB snapshot과 별도로 확인한다.
    payloads = []
    async with RedisEventBus(app.state.redis).subscribe(f"run:{run_id}:events") as subscription:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            await _drain(app, http)
        async with asyncio.timeout(5):
            while True:
                message = await subscription.get_message(timeout=1)
                if message is None:
                    continue
                payload = json.loads(message["data"])
                payloads.append(payload)
                if payload["type"] in {"completed", "failed"}:
                    break

    assert limited_at is not None
    assert github_paths[-1] == blocked_path
    assert github_paths.count(blocked_path) == 1
    assert {path.split("/")[3] for path in github_paths} == {
        f"repo{index}" for index in range(successful_count + 1)
    }
    # TTL 검사는 실제 경과 시간만 허용한다. 값만 저장하거나 잘못된 사용자 키를 쓰면 실패한다.
    assert await app.state.redis.get("gh:rl:501") == b"1"
    ttl = await app.state.redis.ttl("gh:rl:501")
    assert max(1, 90 - math.ceil(time.monotonic() - limited_at) - 1) <= ttl <= 90

    run = await db.get(AnalysisJob, UUID(run_id))
    assert run.status == run_status and run.error_code == "rate_limited"
    assert run.completed_at is not None
    candidates = list(
        await db.scalars(
            select(AnalysisRepoCandidate)
            .where(
                AnalysisRepoCandidate.analysis_job_id == UUID(run_id),
                AnalysisRepoCandidate.batch_no == 1,
            )
            .order_by(AnalysisRepoCandidate.batch_rank)
        )
    )
    assert [row.repository_id for row in candidates] == [repo.id for repo in repositories[:5]]
    snapshots = [row.ranking_signals["analysis"] for row in candidates]
    assert [snapshot["status"] for snapshot in snapshots] == [
        *(["succeeded"] * successful_count),
        *(["failed"] * (5 - successful_count)),
    ]
    assert all(
        snapshot["error_code"] == "rate_limited" and snapshot["analysis_id"] is None
        for snapshot in snapshots[successful_count:]
    )
    assert sum(request.url.host == "api.openai.com" for request in requests) == successful_count

    status = await client.get(f"/api/analysis-runs/{run_id}")
    assert status.status_code == 200
    assert status.json()["status"] == "failed"
    assert status.json()["failureReason"] == "rate_limited"
    result = await client.get(f"/api/analysis-runs/{run_id}/result")
    if successful_count:
        assert result.status_code == 200
        assert result.json()["analyzedCount"] == 1 and result.json()["failedCount"] == 4
        cards = result.json()["repositories"]
        # 제한은 접근 불가 판정이 아니다. 실패 카드도 남기되 추천·분석 성공으로 보이지 않는다.
        assert [card["id"] for card in cards] == [str(repo.id) for repo in repositories[:5]]
        assert cards[0]["status"] == "succeeded"
        assert all(
            card["status"] == "failed"
            and card["errorCode"] == "rate_limited"
            and card["recommended"] is False
            for card in cards[1:]
        )
        assert {item["repositoryId"] for item in result.json()["failedRepositories"]} == {
            str(repo.id) for repo in repositories[1:5]
        }
        assert {item["errorCode"] for item in result.json()["failedRepositories"]} == {
            "rate_limited"
        }
    else:
        assert result.status_code == 409 and result.json()["error"]["reason"] == "not_ready"

    assert payloads[-1] == {"type": "failed", "reason": "rate_limited"}
    steps = [payload for payload in payloads if payload["type"] == "step"]
    assert {"type": "step", "step": "repo_detail", "status": "completed"} in steps
    assert {"type": "step", "step": "repo_analyze", "status": "running"} in steps
    assert all(set(payload) == {"type", "step", "status"} for payload in steps)

    # 재접속 SSE도 같은 실패 원인과 최종 단계 상태를 DB에서 복원해야 한다.
    response = await client.get(f"/api/analysis-runs/{run_id}/events")
    assert response.status_code == 200 and "event:" not in response.text
    events = [
        json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")
    ]
    assert events[-1] == {"type": "failed", "reason": "rate_limited"}
    assert {event["key"]: event["status"] for event in events if event["type"] == "step"} == {
        step["key"]: step["status"] for step in run.steps
    }
