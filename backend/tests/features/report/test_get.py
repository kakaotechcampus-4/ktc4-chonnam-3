"""GET /interviews/{id}/report 200 / 404 / 401 — 저장된 리포트 응답과 소유권.

생성 흐름(202/409/lock)은 test_generate.py. task-16
"""

import uuid

import pytest

from ..interview.factories import make_interview, make_repo, make_run, make_turn, make_user
from .factories import make_disagreement, make_report


def url(interview_id) -> str:
    return f"/api/interviews/{interview_id}/report"


async def test_200_returns_stored_report(client, db, ctx) -> None:
    interview, repo = ctx
    report = await make_report(db, interview)
    await make_disagreement(db, report, "hr_manager")
    await db.commit()

    response = await client.get(url(interview.id))

    assert response.status_code == 200
    body = response.json()
    assert body["interviewId"] == str(interview.id)
    assert [s["key"] for s in body["scores"]][0] == "project_understanding"
    assert body["scores"][0] == {
        "key": "project_understanding",
        "label": "프로젝트 이해도",
        "score": 80.0,
    }
    assert len(body["scores"]) == 6
    assert body["totalScore"] == 75.0  # (80+70+60+90+50+100)/6
    assert body["coverage"] == {
        "totalRequirements": 8,
        "coveredRequirements": 5,
        "uncoveredRequirements": ["Kafka"],
    }
    assert {f["persona"]: f["disagreementSubmitted"] for f in body["agentFeedbacks"]} == {
        "tech_lead": False,
        "hr_manager": True,
        "domain_lead": False,
    }
    assert body["turns"] == [
        {"turn": 1, "persona": "tech_lead", "question": "질문 1", "answer": "답변 1"}
    ]
    assert body["repositoryNames"] == [repo.name]
    assert body["headline"] == "헤드라인"


async def test_200_does_not_enqueue(client, db, ctx, enqueue) -> None:
    interview, _ = ctx
    await make_report(db, interview)
    await db.commit()
    assert (await client.get(url(interview.id))).status_code == 200
    enqueue.assert_not_called()


async def test_404_for_other_users_interview(client, db, ctx, enqueue) -> None:
    other = await make_user(db)
    run = await make_run(db, other)
    theirs = await make_interview(db, run, [await make_repo(db, run)], status="completed")
    await make_turn(db, theirs, 1, answered=True)
    await db.commit()

    response = await client.get(url(theirs.id))

    assert response.status_code == 404
    assert response.json()["error"]["reason"] == "not_found"
    enqueue.assert_not_called()


@pytest.mark.parametrize("interview_id", [str(uuid.uuid4()), "not-a-uuid"])
async def test_404_unknown_id(client, ctx, interview_id) -> None:
    response = await client.get(url(interview_id))
    assert response.status_code == 404
    assert response.json()["error"]["reason"] == "not_found"


async def test_requires_login(client) -> None:
    response = await client.get(url(uuid.uuid4()))
    assert response.status_code == 401
    assert response.json()["error"]["reason"] == "unauthenticated"
