"""POST /interviews HTTP 경계 — 인증·상태코드·envelope. 검사 규칙 자체는 test_service.

main.py 에 아직 등록하지 않으므로 테스트 앱에만 router 를 붙인다.
task-13
"""

import json
import uuid

import pytest

from app.db.models import InterviewSession
from app.features.interview.router import router

from .factories import make_repo, make_run, make_user


@pytest.fixture(autouse=True)
def _mount(app):
    app.include_router(router, prefix=app.state.settings.api_prefix)


@pytest.fixture
async def run(app, db, client):
    run = await make_run(db, await make_user(db))
    await db.commit()
    client.cookies.set("devon_session", await app.state.sessions.create(run.user_id))
    return run


async def test_create_201(client, db, redis, run) -> None:
    repo = await make_repo(db, run)
    await db.commit()

    response = await client.post(
        "/api/interviews", json={"runId": str(run.id), "repositoryIds": [str(repo.id)]}
    )

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"sessionId", "interviewId"}
    stored = json.loads(await redis.get(f"rt:{body['sessionId']}"))
    assert stored == {"interviewId": body["interviewId"], "userId": str(run.user_id)}


async def test_create_requires_login(client) -> None:
    response = await client.post(
        "/api/interviews", json={"runId": str(uuid.uuid4()), "repositoryIds": []}
    )
    assert response.status_code == 401
    assert response.json()["error"]["reason"] == "unauthenticated"


@pytest.mark.parametrize(
    ("payload", "status", "reason"),
    [
        ({"repositoryIds": []}, 400, "no_repository_selected"),
        ({"repositoryIds": ["not-a-uuid"]}, 400, "invalid_request"),
    ],
)
async def test_create_error_envelope(client, run, payload, status, reason) -> None:
    response = await client.post("/api/interviews", json={"runId": str(run.id), **payload})
    assert response.status_code == status
    assert response.json()["error"]["reason"] == reason


async def test_get_after_create(client, db, run) -> None:
    repo = await make_repo(db, run)
    await db.commit()
    created = (
        await client.post(
            "/api/interviews", json={"runId": str(run.id), "repositoryIds": [str(repo.id)]}
        )
    ).json()

    response = await client.get(f"/api/interviews/{created['interviewId']}")

    assert response.status_code == 200
    body = response.json()
    assert body["sessionId"] == created["sessionId"]  # 새로고침해도 같은 WS 키
    assert {k: body[k] for k in ("id", "runId", "status", "repositoryNames", "turns")} == {
        "id": created["interviewId"],
        "runId": str(run.id),
        "status": "preparing",
        "repositoryNames": [repo.name],
        "turns": [],
    }
    assert body["lastError"] is None


@pytest.mark.parametrize("interview_id", [str(uuid.uuid4()), "not-a-uuid"])
async def test_get_not_found(client, run, interview_id) -> None:
    response = await client.get(f"/api/interviews/{interview_id}")
    assert response.status_code == 404
    assert response.json()["error"]["reason"] == "not_found"


async def test_prepare_retry_204(client, db, run) -> None:
    repo = await make_repo(db, run)
    await db.commit()
    created = (
        await client.post(
            "/api/interviews", json={"runId": str(run.id), "repositoryIds": [str(repo.id)]}
        )
    ).json()
    interview = await db.get(InterviewSession, uuid.UUID(created["interviewId"]))
    interview.status = "preparing_failed"
    await db.commit()

    response = await client.post(f"/api/interviews/{created['interviewId']}/prepare/retry")

    assert response.status_code == 204


async def test_prepare_retry_unknown_id_410(client, run) -> None:
    response = await client.post("/api/interviews/not-a-uuid/prepare/retry")
    assert response.status_code == 410
    assert response.json()["error"]["reason"] == "session_expired"
