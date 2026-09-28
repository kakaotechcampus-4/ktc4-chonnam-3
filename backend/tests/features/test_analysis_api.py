"""실제 세션·PostgreSQL·Redis로 분석 API의 중복과 소유권 경계를 확인한다."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from arq.jobs import Job
from sqlalchemy import select

from app.db.models.analysis import AnalysisJob
from app.db.models.document import UserDocument
from app.db.models.user import GithubAccount, User


@pytest.fixture
async def member(db, app, client):
    user = User(name="Analysis user")
    db.add(user)
    await db.flush()
    db.add(
        GithubAccount(
            user_id=user.id,
            github_user_id=501,
            login="analysis-user",
            access_token_encrypted=app.state.cipher.encrypt("private-token"),
            token_status="valid",
            token_scope="read:user",
        )
    )
    await db.commit()
    client.cookies.set("devon_session", await app.state.sessions.create(user.id))
    return user


async def test_create_normalizes_input_deduplicates_and_queues_once(client, member, db, app):
    responses = await asyncio.gather(
        *[
            client.post("/api/analysis-runs", json={"postingUrl": url})
            for url in [
                "https://www.wanted.co.kr/wd/123?utm_source=test",
                "https://www.wanted.co.kr/wd/123",
            ]
        ]
    )
    assert sorted(r.status_code for r in responses) == [202, 409]
    accepted = next(r for r in responses if r.status_code == 202)
    run_id = accepted.json()["runId"]
    duplicate = next(r for r in responses if r.status_code == 409)
    assert duplicate.json()["error"]["details"] == {"runId": run_id}
    assert duplicate.json()["error"]["reason"] == "run_in_progress"
    assert accepted.headers["location"] == f"/api/analysis-runs/{run_id}"
    run = await db.get(AnalysisJob, UUID(run_id))
    assert run.posting_url == "https://www.wanted.co.kr/wd/123"
    assert run.status == "queued" and run.fingerprint
    info = await Job(f"analysis_run:{run_id}", app.state.redis).info()
    assert info.function == "analysis_run" and info.args == (run_id,)
    status = await client.get(f"/api/analysis-runs/{run_id}")
    body = status.json()
    assert status.status_code == 200 and body["status"] == "running"
    assert len(body["steps"]) == 7 and body["steps"][0]["status"] == "skipped"
    assert body["progress"] == 0 and body["failureReason"] is None
    assert "private-token" not in status.text


async def test_distinct_fingerprints_can_run_for_same_user(client, member):
    first = await client.post(
        "/api/analysis-runs", json={"postingUrl": "https://wanted.co.kr/wd/1"}
    )
    second = await client.post(
        "/api/analysis-runs", json={"postingUrl": "https://wanted.co.kr/wd/2"}
    )
    assert first.status_code == second.status_code == 202
    assert first.json()["runId"] != second.json()["runId"]


async def test_large_positive_page_is_empty_not_database_overflow(client, member, db):
    created = await client.post(
        "/api/analysis-runs", json={"postingUrl": "https://wanted.co.kr/wd/1"}
    )
    run = await db.get(AnalysisJob, UUID(created.json()["runId"]))
    run.status = "succeeded"
    await db.commit()
    response = await client.get(f"/api/analysis-runs/{run.id}/candidates?page={2**31}")
    assert response.status_code == 200 and response.json() == {"repositories": []}


@pytest.mark.parametrize(
    "payload,reason",
    [
        ({}, "posting_url_required"),
        ({"postingUrl": ""}, "posting_url_required"),
        ({"postingUrl": "https://example.com/job"}, "unsupported_site"),
    ],
)
async def test_request_validation_uses_existing_error_contract(client, member, payload, reason):
    response = await client.post("/api/analysis-runs", json=payload)
    assert response.status_code == 400
    assert response.json()["error"]["reason"] == reason


async def test_anonymous_cannot_create_or_query(client):
    response = await client.post(
        "/api/analysis-runs", json={"postingUrl": "https://wanted.co.kr/wd/1"}
    )
    assert response.status_code == 401
    assert (await client.get(f"/api/analysis-runs/{uuid4()}")).status_code == 401


async def test_document_owner_and_failed_preview_checked_before_queue(client, member, db):
    other = User(name="Other")
    db.add(other)
    await db.flush()
    doc = UserDocument(
        user_id=other.id,
        filename="portfolio.txt",
        mime_type="text/plain",
        size_bytes=5,
        doc_type="portfolio",
        extract_status="succeeded",
    )
    db.add(doc)
    await db.commit()
    payload = {"postingUrl": "https://wanted.co.kr/wd/1", "documentId": str(doc.id)}
    assert (await client.post("/api/analysis-runs", json=payload)).status_code == 400
    doc.user_id = member.id
    doc.extract_status = "failed"
    await db.commit()
    response = await client.post("/api/analysis-runs", json=payload)
    assert (
        response.status_code == 409
        and response.json()["error"]["reason"] == "document_extract_failed"
    )
    assert list(await db.scalars(select(AnalysisJob))) == []


async def test_terminal_run_allows_new_request_and_expiry_does_not_delete(client, member, db):
    payload = {"postingUrl": "https://wanted.co.kr/wd/123"}
    first = await client.post("/api/analysis-runs", json=payload)
    assert first.status_code == 202
    run = await db.get(AnalysisJob, UUID(first.json()["runId"]))
    run.status = "failed"
    run.error_code = "jd_fetch_failed"
    run.completed_at = datetime.now(UTC)
    await db.commit()
    response = await client.get(f"/api/analysis-runs/{run.id}")
    assert response.status_code == 200 and response.json()["status"] == "failed"
    assert (await client.post("/api/analysis-runs", json=payload)).status_code == 202
    run.created_at = datetime.now(UTC) - timedelta(hours=3)
    await db.commit()
    response = await client.get(f"/api/analysis-runs/{run.id}")
    assert response.status_code == 410
    assert await db.get(AnalysisJob, run.id) is not None


async def test_foreign_and_unknown_runs_share_expired_response(client, member, db):
    other = User(name="Other")
    db.add(other)
    await db.flush()
    run = AnalysisJob(user_id=other.id, job_type="analysis_run", status="succeeded")
    db.add(run)
    await db.commit()
    for identity in (run.id, uuid4()):
        for suffix in ("", "/result", "/candidates?page=1", "/events"):
            response = await client.get(f"/api/analysis-runs/{identity}{suffix}")
            assert response.status_code == 410


async def test_queue_outage_preserves_committed_run_for_reaper(
    client, member, db, app, monkeypatch
):
    async def unavailable(*args, **kwargs):
        raise ConnectionError("queue unavailable")

    monkeypatch.setattr(app.state.redis, "enqueue_job", unavailable)
    response = await client.post(
        "/api/analysis-runs", json={"postingUrl": "https://wanted.co.kr/wd/123"}
    )
    assert response.status_code == 202
    run = await db.get(AnalysisJob, UUID(response.json()["runId"]))
    assert run.status == "queued"
