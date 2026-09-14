"""분석 API — run 생성/중복, 진행률 폴링, result 조회 조건, 후보 page 202.

PostgreSQL 이 필요하다 (conftest 가 없으면 skip). GitHub/Wanted 는 호출하지 않는다.
"""

import uuid
from datetime import timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.analysis import AnalysisJob, AnalysisRepoCandidate
from app.db.models.github import Repository
from app.db.models.user import User
from app.features.analysis.progress import initial_steps
from app.shared.clock import now
from app.shared.enums import (
    STEP_ORDER,
    FilterStatus,
    JobStatus,
    JobType,
    SelectionReason,
    StepKey,
    StepStatus,
)

POSTING_URL = "https://www.wanted.co.kr/wd/123456?ref=search"


async def _create_run(client: AsyncClient, url: str = POSTING_URL) -> dict[str, object]:
    response = await client.post("/api/analysis-runs", json={"postingUrl": url})
    assert response.status_code == 202, response.text
    return response.json()


async def test_create_run_enqueues_analysis_run(client: AsyncClient, arq, db: AsyncSession) -> None:
    body = await _create_run(client)
    assert body["status"] == "running"
    assert body["reused"] is False
    assert arq.jobs == [("analysis_run", (body["runId"],))]

    job = await db.get(AnalysisJob, uuid.UUID(str(body["runId"])))
    assert job is not None
    assert job.job_type == JobType.ANALYSIS_RUN
    assert job.status == JobStatus.QUEUED
    assert job.normalized_posting_url == "https://www.wanted.co.kr/wd/123456"
    assert job.expires_at is not None


async def test_same_fingerprint_reuses_run(client: AsyncClient, arq) -> None:
    first = await _create_run(client)
    # query string 이 달라도 normalized URL 이 같으면 같은 fingerprint 다.
    second = await _create_run(client, "https://www.wanted.co.kr/wd/123456")
    assert second["runId"] == first["runId"]
    assert second["reused"] is True
    assert len(arq.jobs) == 1


async def test_different_posting_while_running_is_conflict(client: AsyncClient) -> None:
    first = await _create_run(client)
    response = await client.post(
        "/api/analysis-runs", json={"postingUrl": "https://www.wanted.co.kr/wd/999"}
    )
    assert response.status_code == 409
    body = response.json()
    assert body["error"]["reason"] == "run_in_progress"
    assert body["error"]["details"]["runId"] == first["runId"]


@pytest.mark.parametrize(
    ("url", "reason"),
    [
        ("", "posting_url_required"),
        ("https://www.jobkorea.co.kr/Recruit/GI_Read/1", "unsupported_site"),
    ],
)
async def test_posting_url_validation(client: AsyncClient, url: str, reason: str) -> None:
    response = await client.post("/api/analysis-runs", json={"postingUrl": url})
    assert response.status_code == 400
    assert response.json()["error"]["reason"] == reason


async def test_unknown_document_is_rejected(client: AsyncClient) -> None:
    response = await client.post(
        "/api/analysis-runs",
        json={"postingUrl": POSTING_URL, "documentId": str(uuid.uuid4())},
    )
    assert response.status_code == 400
    assert response.json()["error"]["reason"] == "document_not_found"


async def test_run_status_polling_reports_steps(client: AsyncClient, db: AsyncSession) -> None:
    body = await _create_run(client)
    run_id = uuid.UUID(str(body["runId"]))
    job = await db.get(AnalysisJob, run_id)
    assert job is not None
    steps = initial_steps()
    steps[str(StepKey.DOC_EXTRACT)] = str(StepStatus.SUCCEEDED)
    steps[str(StepKey.REPO_SELECT)] = str(StepStatus.RUNNING)
    job.steps = steps
    job.status = str(JobStatus.RUNNING)
    job.progress = 21
    await db.commit()

    response = await client.get(f"/api/analysis-runs/{run_id}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "running"
    assert payload["progress"] == 21
    assert [step["key"] for step in payload["steps"]] == [str(key) for key in STEP_ORDER]
    assert payload["steps"][0]["status"] == "succeeded"
    assert payload["failureReason"] is None


async def test_failed_run_is_http_200_with_reason(client: AsyncClient, db: AsyncSession) -> None:
    body = await _create_run(client)
    job = await db.get(AnalysisJob, uuid.UUID(str(body["runId"])))
    assert job is not None
    job.status = str(JobStatus.FAILED)
    job.error_code = "jd_fetch_failed"
    await db.commit()

    response = await client.get(f"/api/analysis-runs/{job.id}")
    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert response.json()["failureReason"] == "jd_fetch_failed"


async def test_unknown_run_is_404(client: AsyncClient) -> None:
    response = await client.get(f"/api/analysis-runs/{uuid.uuid4()}")
    assert response.status_code == 404
    assert response.json()["error"]["reason"] == "not_found"


async def test_result_requires_finished_run(client: AsyncClient, db: AsyncSession) -> None:
    body = await _create_run(client)
    run_id = uuid.UUID(str(body["runId"]))
    response = await client.get(f"/api/analysis-runs/{run_id}/result")
    assert response.status_code == 409
    assert response.json()["error"]["reason"] == "not_ready"

    job = await db.get(AnalysisJob, run_id)
    assert job is not None
    job.expires_at = now() - timedelta(seconds=1)
    await db.commit()
    expired = await client.get(f"/api/analysis-runs/{run_id}/result")
    assert expired.status_code == 410
    assert expired.json()["error"]["reason"] == "run_expired"


async def test_partial_run_result_is_readable(
    client: AsyncClient, db: AsyncSession, user: User
) -> None:
    body = await _create_run(client)
    run_id = uuid.UUID(str(body["runId"]))
    job = await db.get(AnalysisJob, run_id)
    assert job is not None

    ok_repo = _repository(user, "kim/project-a", detail=True)
    failed_repo = _repository(user, "kim/project-b", detail=False, error_code="rate_limited")
    db.add_all([ok_repo, failed_repo])
    await db.flush()
    db.add_all(
        [
            _candidate(job.id, ok_repo.id, base_rank=1, batch_rank=1),
            _candidate(job.id, failed_repo.id, base_rank=2, batch_rank=2),
        ]
    )
    job.status = str(JobStatus.PARTIAL)
    job.error_code = "rate_limited"
    await db.commit()

    response = await client.get(f"/api/analysis-runs/{run_id}/result")
    assert response.status_code == 200
    payload = response.json()
    # DB partial -> FE failed 이지만 result 는 조회된다.
    assert payload["status"] == "failed"
    assert payload["analyzedCount"] == 1
    assert payload["failedCount"] == 1
    assert payload["failedRepositories"][0]["errorCode"] == "rate_limited"
    cards = {card["fullName"]: card for card in payload["repositories"]}
    assert cards["kim/project-a"]["status"] == "succeeded"
    assert cards["kim/project-a"]["matchScore"] is None
    assert cards["kim/project-b"]["status"] == "failed"


async def test_candidate_page_enqueues_once(
    client: AsyncClient, db: AsyncSession, user: User, arq
) -> None:
    body = await _create_run(client)
    run_id = uuid.UUID(str(body["runId"]))
    job = await db.get(AnalysisJob, run_id)
    assert job is not None
    job.status = str(JobStatus.SUCCEEDED)

    repos = [_repository(user, f"kim/repo-{i}", detail=False) for i in range(12)]
    db.add_all(repos)
    await db.flush()
    for index, repo in enumerate(repos, start=1):
        db.add(
            _candidate(
                job.id,
                repo.id,
                base_rank=index,
                batch_rank=index if index <= 10 else None,
                batch_no=1 if index <= 10 else None,
            )
        )
    await db.commit()

    first = await client.get(f"/api/analysis-runs/{run_id}/candidates", params={"page": 1})
    assert first.status_code == 200
    assert len(first.json()["repositories"]) == 10

    second = await client.get(f"/api/analysis-runs/{run_id}/candidates", params={"page": 2})
    assert second.status_code == 202
    assert second.json() == {"status": "analyzing", "retryAfter": 3}
    page_jobs = [job_name for job_name, _ in arq.jobs if job_name == "candidate_page_analyze"]
    assert len(page_jobs) == 1

    # 재요청해도 lock 때문에 중복 enqueue 되지 않는다.
    again = await client.get(f"/api/analysis-runs/{run_id}/candidates", params={"page": 2})
    assert again.status_code == 202
    page_jobs = [job_name for job_name, _ in arq.jobs if job_name == "candidate_page_analyze"]
    assert len(page_jobs) == 1


def _repository(
    user: User, full_name: str, *, detail: bool, error_code: str | None = None
) -> Repository:
    return Repository(
        user_id=user.id,
        github_repo_id=abs(hash(full_name)) % 10**9,
        full_name=full_name,
        name=full_name.split("/")[-1],
        html_url=f"https://github.com/{full_name}",
        primary_language="Python",
        topics=["api"],
        stars=3,
        forks=1,
        size_kb=300,
        is_private=False,
        is_fork=False,
        is_archived=False,
        repo_pushed_at=now(),
        languages={"Python": 800, "Shell": 200} if detail else None,
        readme_truncated=False,
        commit_count=42 if detail else None,
        user_commit_count=40 if detail else None,
        fetch_level="detail" if detail else "list",
        fetch_error_code=error_code,
    )


def _candidate(
    job_id: uuid.UUID,
    repository_id: uuid.UUID,
    *,
    base_rank: int,
    batch_rank: int | None,
    batch_no: int | None = 1,
) -> AnalysisRepoCandidate:
    return AnalysisRepoCandidate(
        analysis_job_id=job_id,
        repository_id=repository_id,
        base_rank=base_rank,
        batch_no=batch_no,
        batch_rank=batch_rank,
        selection_reason=str(SelectionReason.BASE_RANK_TOP),
        ranking_score=1.0,
        ranking_signals={"portfolio_mentioned": False, "rule_filter_passed": True},
        filter_status=str(FilterStatus.ELIGIBLE),
    )
