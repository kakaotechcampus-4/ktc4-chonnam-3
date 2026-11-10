"""Login landing reads real user-owned records, never provider credentials."""

import importlib
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.db.models.analysis import AnalysisJob
from app.db.models.github import Repository, UserProfileSummary
from app.db.models.interview import InterviewSession, InterviewTurn
from app.db.models.posting import JobPosting
from app.db.models.report import InterviewReport
from app.db.models.user import GithubAccount, User


def _answered_turns(interview, count, personas=("tech_lead",)):
    """답변 완료 턴 count개. 면접관은 personas 를 돌려 가며 배정한다."""
    return [
        InterviewTurn(
            interview_session_id=interview.id,
            turn_no=number,
            persona=personas[(number - 1) % len(personas)],
            status="answered",
            question_text=f"Q{number}",
            answer_text=f"A{number}",
        )
        for number in range(1, count + 1)
    ]


def test_identity_serializer_rejects_account_or_provider_secrets():
    module = importlib.import_module("app.features.me.schemas")
    assert hasattr(module, "MeResponse"), "Identity response must be implemented"
    public = {"name": "User", "avatar_url": None, "github_linked": True}
    response = module.MeResponse.model_validate(public)
    assert response.model_dump(by_alias=True) == {
        "name": "User",
        "avatarUrl": None,
        "githubLinked": True,
    }
    # 공통 CamelModel은 미정의 필드를 거부한다. 비밀값을 전달한 실수도 숨기지 않는다.
    with pytest.raises(ValidationError) as caught:
        module.MeResponse.model_validate(
            {**public, "access_token_encrypted": b"secret", "github_user_id": 123}
        )
    assert {error["type"] for error in caught.value.errors()} == {"extra_forbidden"}


@pytest.fixture
async def member(db, app, client):
    user = User(name="Session user", avatar_url=None)
    db.add(user)
    await db.flush()
    db.add(
        GithubAccount(
            user_id=user.id,
            github_user_id=71,
            login="session-user",
            public_repo_count=0,
            access_token_encrypted=app.state.cipher.encrypt("never-public-token"),
            token_status="valid",
            token_scope="read:user",
        )
    )
    await db.commit()
    sid = await app.state.sessions.create(user.id)
    client.cookies.set("devon_session", sid)
    return user


async def test_current_user_and_empty_landing_contract(client, member):
    response = await client.get("/api/me")
    assert response.status_code == 200
    assert response.json() == {"name": "Session user", "avatarUrl": None, "githubLinked": True}
    assert "never-public-token" not in response.text
    home = await client.get("/api/me/home")
    assert home.status_code == 200
    assert home.json() == {
        "name": "Session user",
        "githubLinked": True,
        "repositoryCount": 0,
        "analysisStatus": "no_repository",
        "analysis": None,
        "recentInterviews": [],
    }
    profile = (await client.get("/api/me/profile")).json()
    assert profile["loginId"] == "session-user"
    assert profile["avatarUrl"] == ""
    assert profile["desiredPosition"] is None
    assert profile["interviewSummary"] == {"totalCount": 0, "averageScore": None}
    assert (await client.get("/api/me/interviews")).json() == {
        "interviews": [],
        "total": 0,
        "page": 1,
        "size": 20,
        "averageScore": None,
    }


async def test_home_distinguishes_sync_pending_failed_and_completed(client, member, db):
    job = AnalysisJob(user_id=member.id, job_type="initial_sync", status="queued")
    db.add(job)
    await db.commit()
    assert (await client.get("/api/me/home")).json()["analysisStatus"] == "syncing"
    job.status = "failed"
    job.error_code = "repo_unreachable"
    await db.commit()
    failed = await client.get("/api/me/home")
    assert failed.status_code == 500
    assert failed.json()["error"]["reason"] == "internal_error"
    job.status = "succeeded"
    db.add(Repository(user_id=member.id, github_repo_id=1, name="repo", full_name="u/repo"))
    await db.commit()
    assert (await client.get("/api/me/home")).json()["analysisStatus"] == "no_interview"


async def test_profile_and_history_are_completed_only_and_user_scoped(client, member, db):
    posting = JobPosting(
        normalized_url="https://wanted.co.kr/wd/19",
        raw_url="https://wanted.co.kr/wd/19",
        position="Backend engineer",
        company_name="Example",
        parse_status="succeeded",
    )
    other = User(name="Other user")
    db.add_all([posting, other])
    await db.flush()
    jobs = [
        AnalysisJob(user_id=user.id, job_type="analysis_run", status="succeeded")
        for user in (member, other)
    ]
    db.add_all(jobs)
    await db.flush()
    mine = InterviewSession(
        user_id=member.id,
        analysis_job_id=jobs[0].id,
        job_posting_id=posting.id,
        status="completed",
        completed_at=datetime.now(UTC),
    )
    foreign = InterviewSession(
        user_id=other.id,
        analysis_job_id=jobs[1].id,
        job_posting_id=posting.id,
        status="completed",
        completed_at=datetime.now(UTC),
    )
    # 완료 여부·소유권과 무관하게 모든 면접에는 공고가 있어야 한다.
    abandoned = InterviewSession(
        user_id=member.id,
        analysis_job_id=jobs[0].id,
        job_posting_id=posting.id,
        status="abandoned",
    )
    db.add_all([mine, foreign, abandoned])
    await db.flush()
    db.add_all(_answered_turns(mine, 9))  # 평균은 모든 턴에 답한 면접만 센다
    db.add_all(
        [
            InterviewReport(
                interview_session_id=mine.id, headline="Report", summary="Summary", total_score=80
            ),
            InterviewReport(
                interview_session_id=foreign.id, headline="Other", summary="Private", total_score=20
            ),
            UserProfileSummary(
                user_id=member.id, based_on_repo_count=1, role_summary="Stored summary"
            ),
            Repository(user_id=member.id, github_repo_id=1, name="mine", full_name="user/mine"),
        ]
    )
    await db.commit()
    history = (await client.get("/api/me/interviews?size=1")).json()
    assert history["total"] == 1
    assert history["averageScore"] == 80
    assert [row["id"] for row in history["interviews"]] == [str(mine.id)]
    assert history["interviews"][0]["answeredTurns"] == 9
    assert history["interviews"][0]["reportAvailable"] is True  # 리포트가 있다
    profile = (await client.get("/api/me/profile")).json()
    assert profile["desiredPosition"] == "Backend engineer"
    assert profile["interviewSummary"] == {"totalCount": 1, "averageScore": 80}
    home = (await client.get("/api/me/home")).json()
    assert home["analysisStatus"] == "completed"
    assert home["analysis"]["roleSummary"] == "Stored summary"
    assert [item["id"] for item in home["recentInterviews"]] == [str(mine.id)]


async def test_average_leaves_out_interviews_that_ran_out_of_time(client, member, db):
    """시간 종료 면접은 횟수·목록에는 남고 평균에서만 빠진다. 리포트를 만들 수 없으면 표시한다."""
    posting = JobPosting(
        normalized_url="https://wanted.co.kr/wd/20",
        raw_url="https://wanted.co.kr/wd/20",
        parse_status="succeeded",
    )
    db.add(posting)
    await db.flush()
    job = AnalysisJob(user_id=member.id, job_type="analysis_run", status="succeeded")
    db.add(job)
    await db.flush()
    both = ("tech_lead", "domain_lead")
    # 이름 -> (답변 완료 턴 수, 면접관, 리포트 점수(없으면 None))
    cases = {
        "full": (9, both, 60),
        "early_with_report": (5, both, 95),
        "early_not_opened": (3, both, None),  # 열면 만들어지지만 아직 안 열었다(지연 생성)
        "too_short": (2, ("tech_lead",), None),  # domain_lead 질문에 답하지 못했다
    }
    interviews = {}
    for index, (name, (answered, personas, score)) in enumerate(cases.items()):
        interview = InterviewSession(
            user_id=member.id,
            analysis_job_id=job.id,
            job_posting_id=posting.id,
            status="completed",
            completed_at=datetime(2026, 11, 10 + index, tzinfo=UTC),
        )
        db.add(interview)
        await db.flush()
        db.add_all(_answered_turns(interview, answered, personas))
        if score is not None:
            db.add(
                InterviewReport(
                    interview_session_id=interview.id,
                    headline="Report",
                    summary="Summary",
                    total_score=score,
                )
            )
        interviews[name] = interview
    await db.commit()

    history = (await client.get("/api/me/interviews")).json()

    assert history["total"] == 4
    assert history["averageScore"] == 60  # 95점 면접은 5턴만 답해 평균에 넣지 않는다
    rows = {row["id"]: row for row in history["interviews"]}
    shown = {
        name: (row["answeredTurns"], row["totalScore"], row["reportAvailable"])
        for name, interview in interviews.items()
        for row in [rows[str(interview.id)]]
    }
    assert shown == {
        "full": (9, 60, True),
        "early_with_report": (5, 95, True),  # 점수 자체는 그대로 보인다
        "early_not_opened": (3, None, True),
        "too_short": (2, None, False),
    }
    profile = (await client.get("/api/me/profile")).json()
    assert profile["interviewSummary"] == {"totalCount": 4, "averageScore": 60}


async def test_abandoned_interview_is_never_report_available(client, member, db):
    """중단된 면접은 tech·domain 답변이 있어도 리포트를 만들 수 없다."""
    posting = JobPosting(
        normalized_url="https://wanted.co.kr/wd/21",
        raw_url="https://wanted.co.kr/wd/21",
        parse_status="succeeded",
    )
    db.add(posting)
    await db.flush()
    job = AnalysisJob(user_id=member.id, job_type="analysis_run", status="succeeded")
    db.add(job)
    await db.flush()
    interview = InterviewSession(
        user_id=member.id,
        analysis_job_id=job.id,
        job_posting_id=posting.id,
        status="abandoned",
        started_at=datetime(2026, 11, 10, tzinfo=UTC),
    )
    db.add(interview)
    await db.flush()
    db.add_all(_answered_turns(interview, 3, ("tech_lead", "domain_lead")))
    await db.commit()

    row = (await client.get("/api/me/interviews")).json()["interviews"][0]

    assert (row["status"], row["answeredTurns"], row["reportAvailable"]) == ("abandoned", 3, False)


async def test_landing_requires_session_and_revoked_github_is_separate(client, member, db):
    from sqlalchemy import update

    await db.execute(
        update(GithubAccount)
        .where(GithubAccount.user_id == member.id)
        .values(token_status="revoked")
    )
    await db.commit()
    assert (await client.get("/api/me")).json()["githubLinked"] is False
    assert (await client.get("/api/me/home")).status_code == 403
    assert (await client.get("/api/me/profile")).status_code == 200
    client.cookies.clear()
    for path in ("/api/me", "/api/me/home", "/api/me/profile", "/api/me/interviews"):
        assert (await client.get(path)).status_code == 401


async def test_history_lists_started_abandoned_with_completed_total_and_order(client, member, db):
    posting = JobPosting(
        normalized_url="https://wanted.co.kr/wd/21",
        raw_url="https://wanted.co.kr/wd/21",
        position="Backend engineer",
        company_name="Example",
        parse_status="succeeded",
    )
    db.add(posting)
    await db.flush()
    job = AnalysisJob(user_id=member.id, job_type="analysis_run", status="succeeded")
    db.add(job)
    await db.flush()
    now = datetime.now(UTC)
    completed = InterviewSession(
        user_id=member.id,
        analysis_job_id=job.id,
        job_posting_id=posting.id,
        status="completed",
        started_at=now - timedelta(hours=3),
        completed_at=now - timedelta(hours=2),
    )
    # 첫 질문 뒤 중단: 이력에 포함되고 정렬 기준은 started_at 이다.
    started_abandoned = InterviewSession(
        user_id=member.id,
        analysis_job_id=job.id,
        job_posting_id=posting.id,
        status="abandoned",
        started_at=now - timedelta(hours=1),
        abandoned_at=now - timedelta(minutes=50),
    )
    # 첫 질문 전 중단: 이력에 넣지 않는다.
    unstarted_abandoned = InterviewSession(
        user_id=member.id,
        analysis_job_id=job.id,
        job_posting_id=posting.id,
        status="abandoned",
        abandoned_at=now,
    )
    db.add_all([completed, started_abandoned, unstarted_abandoned])
    await db.flush()
    db.add_all(_answered_turns(completed, 9))  # 평균은 모든 턴에 답한 면접만 센다
    db.add(
        InterviewReport(
            interview_session_id=completed.id, headline="Report", summary="Summary", total_score=70
        )
    )
    await db.commit()

    history = (await client.get("/api/me/interviews")).json()
    assert history["total"] == 2
    assert history["averageScore"] == 70
    assert [(row["id"], row["status"]) for row in history["interviews"]] == [
        (str(started_abandoned.id), "abandoned"),
        (str(completed.id), "completed"),
    ]
    assert history["interviews"][0]["totalScore"] is None
    assert history["interviews"][0]["completedAt"] is None
    # 프로필 횟수·홈 최근 면접은 지금처럼 완료 면접만 센다.
    profile = (await client.get("/api/me/profile")).json()
    assert profile["interviewSummary"] == {"totalCount": 1, "averageScore": 70}
