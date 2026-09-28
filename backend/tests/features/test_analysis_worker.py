"""실제 ARQ·PostgreSQL·Redis와 HTTP mock으로 분석 파이프라인을 검증한다."""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock
from uuid import UUID

import httpx
import pytest
from arq.jobs import Job
from arq.worker import Worker
from pydantic import SecretStr
from sqlalchemy import func, select

from app.db.models.analysis import AnalysisJob, AnalysisRepoCandidate, AnalysisRepoCandidatePage
from app.db.models.document import UserDocument
from app.db.models.github import RepoAnalysis, Repository
from app.db.models.knowledge import PromptVersion
from app.features.analysis.queue import enqueue_analysis
from tests.features.test_analysis_api import member as member

# 선행 테스트 패키지 유무와 무관하게 재사용 fixture의 import 묶음을 유지한다.
# isort: split
from tests.features.analysis.test_repo_analyze import _github_reply, _model_reply
from tests.features.test_postings import PAYLOAD


@pytest.fixture
def app_settings(app_settings):
    return app_settings.model_copy(
        update={
            "openai_api_key": SecretStr("mock-model-key"),
            "llm_default_model": "fixture-model",
            "llm_timeout_seconds": 2,
            "llm_max_output_tokens": 4096,
            "llm_max_input_bytes": 65536,
            "llm_max_response_bytes": 65536,
        }
    )


@pytest.fixture
async def repositories(db, member):
    now = datetime.now(UTC)
    db.add(
        AnalysisJob(
            user_id=member.id,
            job_type="initial_sync",
            status="succeeded",
            completed_at=now,
        )
    )
    db.add(
        PromptVersion(
            task_name="repo_shallow",
            version="worker-fixture-v1",
            model="fixture-model",
            template="fixture repository analysis",
            is_active=True,
        )
    )
    rows = [
        Repository(
            user_id=member.id,
            github_repo_id=1000 + index,
            name=f"repo{index}",
            full_name=f"analysis-user/repo{index}",
            description="Python API service",
            primary_language="Python",
            default_branch="main",
            size_kb=100,
            pushed_at=now - timedelta(days=index),
            synced_at=now,
        )
        for index in range(7)
    ]
    db.add_all(rows)
    await db.commit()
    return rows


def _http_handler(*, inaccessible=(), missing_readme=(), posting_failed=False):
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.host == "api.github.com":
            unavailable = "all" in inaccessible or any(
                f"/{name}/" in request.url.path for name in inaccessible
            )
            incomplete = any(f"/{name}/" in request.url.path for name in missing_readme)
            return _github_reply(request, inaccessible=unavailable, missing_readme=incomplete)
        if request.url.host == "www.wanted.co.kr":
            assert request.url.path.endswith("/123/details")
            return httpx.Response(500 if posting_failed else 200, json=PAYLOAD)
        assert request.url.host == "api.openai.com", request.url
        body = json.loads(request.content)
        payload = json.loads(body["input"][0]["content"][0]["text"])
        inputs = payload["repositories"]
        return _model_reply([item["repository_id"] for item in inputs], inputs[0]["head_sha"])

    return handler, requests


async def _start(client, *, document_id=None):
    payload = {"postingUrl": "https://www.wanted.co.kr/wd/123"}
    if document_id is not None:
        payload["documentId"] = str(document_id)
    response = await client.post("/api/analysis-runs", json=payload)
    assert response.status_code == 202, response.text
    return response.json()["runId"]


async def _drain(app, http):
    # 게시용 진입점에 등록된 함수를 실제 ARQ 워커가 실행하는지 확인한다.
    from app.workers.analysis_app import WorkerSettings

    worker = Worker(
        WorkerSettings.functions,
        redis_pool=app.state.redis,
        burst=True,
        keep_result=WorkerSettings.keep_result,
        max_tries=WorkerSettings.max_tries,
        handle_signals=False,
        poll_delay=0.01,
        ctx={
            "session_factory": app.state.session_factory,
            "cipher": app.state.cipher,
            "http_client": http,
            "redis": app.state.redis,
            "settings": app.state.settings,
        },
    )
    await worker.async_run()
    # app fixture가 공유 Redis pool의 수명을 관리한다.
    assert worker.jobs_failed == 0
    return worker


@pytest.mark.parametrize("with_document", [False, True])
async def test_api_to_arq_completes_seven_steps_and_duplicate_delivery_is_noop(
    client, db, app, repositories, with_document
):
    document = None
    if with_document:
        document = UserDocument(
            user_id=repositories[0].user_id,
            filename="portfolio.pdf",
            mime_type="application/pdf",
            size_bytes=100,
            doc_type="portfolio",
            extract_status="succeeded",
            extracted_github_urls=["https://github.com/analysis-user/repo0"],
        )
        db.add(document)
        await db.commit()
    run_id = await _start(client, document_id=document.id if document else None)
    handler, requests = _http_handler()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        assert (await _drain(app, http)).jobs_complete == 1
        status = await client.get(f"/api/analysis-runs/{run_id}")
        body = status.json()
        assert status.status_code == 200 and body["status"] == "completed", body
        assert body["steps"] == [
            {
                "key": key,
                "status": "skipped" if key == "doc_extract" and not with_document else "completed",
            }
            for key in (
                "doc_extract",
                "repo_select",
                "repo_detail",
                "jd_fetch",
                "jd_extract",
                "repo_analyze",
                "match_score",
            )
        ]
        assert body["progress"] == 100 and body["failureReason"] is None
        result = await client.get(f"/api/analysis-runs/{run_id}/result")
        assert result.status_code == 200, result.text
        assert result.json()["analyzedCount"] == 5
        assert result.json()["failedCount"] == 0
        assert result.json()["failedRepositories"] == []
        assert result.json()["mentionedRepoCount"] == int(with_document)
        assert result.json()["matchedRepoCount"] == int(with_document)
        assert len(result.json()["repositories"]) == 5
        assert result.json()["jdRequirements"]
        hosts = [request.url.host for request in requests]
        assert (
            hosts.index("api.github.com")
            < hosts.index("www.wanted.co.kr")
            < hosts.index("api.openai.com")
        )
        before = len(requests)
        await app.state.redis.enqueue_job("analysis_run", run_id, _job_id=f"duplicate:{run_id}")
        await _drain(app, http)
        assert len(requests) == before
    run = await db.get(AnalysisJob, UUID(run_id))
    assert run.status == "succeeded" and run.completed_at >= run.started_at >= run.queued_at
    assert run.duration_ms >= 0 and run.queue_wait_ms >= 0
    assert await db.scalar(select(func.count()).select_from(RepoAnalysis)) == 5


async def test_candidate_page_is_enqueued_once_and_keeps_completed_run(
    client, db, app, repositories
):
    run_id = await _start(client)
    handler, _ = _http_handler()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        await _drain(app, http)
        responses = await asyncio.gather(
            *[client.get(f"/api/analysis-runs/{run_id}/candidates?page=2") for _ in range(3)]
        )
        assert all(response.status_code == 202 for response in responses)
        assert all(
            response.json() == {"status": "analyzing", "retryAfter": 3} for response in responses
        )
        assert await app.state.redis.zcard("arq:queue") == 1
        info = await Job(f"candidate_page_analyze:{run_id}:2", app.state.redis).info()
        assert info.function == "candidate_page_analyze" and info.args == (run_id, 2)
        assert (await client.get(f"/api/analysis-runs/{run_id}")).json()["status"] == "completed"
        assert (await _drain(app, http)).jobs_complete == 1
    response = await client.get(f"/api/analysis-runs/{run_id}/candidates?page=2")
    assert response.status_code == 200, response.text
    assert len(response.json()["repositories"]) == 2
    assert (await client.get(f"/api/analysis-runs/{run_id}")).json()["status"] == "completed"
    result = await client.get(f"/api/analysis-runs/{run_id}/result")
    assert result.json()["analyzedCount"] == 7
    page = await db.scalar(
        select(AnalysisRepoCandidatePage).where(
            AnalysisRepoCandidatePage.analysis_job_id == UUID(run_id),
            AnalysisRepoCandidatePage.page_no == 2,
        )
    )
    assert page.status == "succeeded" and page.completed_at >= page.started_at >= page.requested_at
    assert page.duration_ms >= 0 and page.queue_wait_ms >= 0
    assert await app.state.redis.zcard("arq:queue") == 0


@pytest.mark.parametrize("all_failed", [False, True])
async def test_inaccessible_failures_keep_assigned_counts_and_terminal_run(
    client, db, app, repositories, all_failed
):
    run_id = await _start(client)
    handler, requests = _http_handler(inaccessible=("all",) if all_failed else ("repo0",))
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        await _drain(app, http)
    status = await client.get(f"/api/analysis-runs/{run_id}")
    assert status.status_code == 200 and status.json()["status"] == "failed"
    run = await db.get(AnalysisJob, UUID(run_id))
    assert run.status == ("failed" if all_failed else "partial")
    result = await client.get(f"/api/analysis-runs/{run_id}/result")
    if all_failed:
        assert result.status_code == 409 and result.json()["error"]["reason"] == "not_ready"
        assert not any(request.url.host == "api.openai.com" for request in requests)
    else:
        assert result.status_code == 200, result.text
        payload = result.json()
        assert payload["analyzedCount"] == 4 and payload["failedCount"] == 1
        assert len(payload["repositories"]) == 4
        assert payload["failedRepositories"] == [
            {"repositoryId": str(repositories[0].id), "errorCode": "repo_unreachable"}
        ]
