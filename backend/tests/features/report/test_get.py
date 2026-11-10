"""GET /interviews/{id}/report 200 / 404 / 401 — 저장된 리포트 응답과 소유권.

생성 흐름(202/409/lock)은 test_generate.py. task-16
"""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import delete, select

from app.db.models import InterviewTurn, JobPosting, ReportScore

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
        {
            "turn": 1,
            "persona": "tech_lead",
            "question": "질문 1",
            "answer": "답변 1",
            "mainIndex": 1,
            "followUpDepth": 0,
        },
        {
            "turn": 2,
            "persona": "domain_lead",
            "question": "질문 2",
            "answer": "답변 2",
            "mainIndex": 2,
            "followUpDepth": 0,
        },
    ]
    assert body["repositoryNames"] == [repo.name]
    assert body["headline"] == "헤드라인"


async def test_report_restores_main_and_follow_up_positions(client, db, ctx) -> None:
    interview, _ = ctx
    # ctx 의 2번 턴(domain_lead)을 1번 턴의 꼬리질문으로 바꾸고 3번 턴을 새 주 질문으로 둔다.
    second = await db.scalar(select(InterviewTurn).where(InterviewTurn.turn_no == 2))
    second.depth, second.parent_turn_no = 2, 1
    await make_turn(db, interview, 3, answered=True, depth=1)
    await make_report(db, interview)
    await db.commit()

    body = (await client.get(url(interview.id))).json()

    assert [(turn["mainIndex"], turn["followUpDepth"]) for turn in body["turns"]] == [
        (1, 0),
        (1, 1),
        (2, 0),
    ]


async def test_200_leaves_out_the_turn_left_unanswered_when_time_ran_out(client, db, ctx) -> None:
    interview, _ = ctx
    await make_report(db, interview)
    await make_turn(db, interview, 3, persona="tech_lead")  # 질문만 받고 시간이 끝났다
    await db.commit()

    body = (await client.get(url(interview.id))).json()

    assert [t["turn"] for t in body["turns"]] == [1, 2]


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


async def test_total_score_rounds_half_up_to_integer(client, db, ctx) -> None:
    interview, _ = ctx
    await make_report(db, interview, scores=(10, 10, 10, 10, 10, 13))  # 평균 10.5
    await db.commit()

    body = (await client.get(url(interview.id))).json()

    assert body["totalScore"] == 11  # 짝수 반올림(10)이 아니라 half-up


async def test_total_score_is_mean_of_scores_not_stored_value(client, db, ctx) -> None:
    interview, _ = ctx
    await make_report(db, interview, total_score=1)  # 저장값은 평균(75)과 다르다
    await db.commit()

    body = (await client.get(url(interview.id))).json()

    assert body["totalScore"] == 75.0


async def test_position_label_and_completed_at(client, db, ctx) -> None:
    interview, _ = ctx
    posting = await db.get(JobPosting, interview.job_posting_id)
    posting.position = "백엔드 개발자"
    posting.company_name = "토스뱅크"
    interview.completed_at = datetime(2026, 9, 1, 15, 20, tzinfo=UTC)
    await make_report(db, interview, generated_at=datetime(2026, 9, 2, tzinfo=UTC))
    await db.commit()

    body = (await client.get(url(interview.id))).json()

    assert body["position"] == "백엔드 개발자"
    assert body["positionLabel"] == "토스뱅크 백엔드 개발자"
    assert body["completedAt"].startswith("2026-09-01T15:20:00")  # generated_at 이 아니다


async def test_position_label_without_company(client, db, ctx) -> None:
    interview, _ = ctx
    posting = await db.get(JobPosting, interview.job_posting_id)
    posting.position = "백엔드 개발자"
    posting.company_name = None
    await make_report(db, interview)
    await db.commit()

    body = (await client.get(url(interview.id))).json()

    assert body["positionLabel"] == "백엔드 개발자"


async def test_500_when_scores_are_not_six(client, db, ctx) -> None:
    interview, _ = ctx
    report = await make_report(db, interview)
    await db.execute(
        delete(ReportScore)
        .where(ReportScore.report_id == report.id)
        .execution_options(synchronize_session=False)
    )
    await db.commit()

    response = await client.get(url(interview.id))

    assert response.status_code == 500
    assert response.json()["error"]["reason"] == "internal_error"


@pytest.mark.parametrize(
    "overrides",
    [
        {"feedback_json": [{"persona": "tech_lead"}]},
        {"coverage_json": None},
        {"coverage_json": {"totalRequirements": "x"}},
    ],
)
async def test_500_when_feedback_or_coverage_is_malformed(client, db, ctx, overrides) -> None:
    interview, _ = ctx
    await make_report(db, interview, **overrides)
    await db.commit()

    response = await client.get(url(interview.id))

    assert response.status_code == 500
    assert response.json()["error"]["reason"] == "internal_error"
