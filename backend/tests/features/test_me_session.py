"""Login landing reads real user-owned records, never provider credentials."""

import importlib
from datetime import UTC, datetime

import pytest

from app.db.models.analysis import AnalysisJob
from app.db.models.github import Repository, UserProfileSummary
from app.db.models.interview import InterviewSession
from app.db.models.posting import JobPosting
from app.db.models.report import InterviewReport
from app.db.models.user import GithubAccount, User


def test_identity_serializer_never_exposes_account_or_provider_secrets():
    module = importlib.import_module("app.features.me.schemas")
    assert hasattr(module, "MeResponse"), "Identity response must be implemented"
    response = module.MeResponse.model_validate(
        {
            "name": "User",
            "avatar_url": None,
            "github_linked": True,
            "access_token_encrypted": b"secret",
            "github_user_id": 123,
        }
    )
    assert response.model_dump(by_alias=True) == {
        "name": "User",
        "avatarUrl": None,
        "githubLinked": True,
    }


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
        status="completed",
        completed_at=datetime.now(UTC),
    )
    abandoned = InterviewSession(user_id=member.id, analysis_job_id=jobs[0].id, status="abandoned")
    db.add_all([mine, foreign, abandoned])
    await db.flush()
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
    profile = (await client.get("/api/me/profile")).json()
    assert profile["desiredPosition"] == "Backend engineer"
    assert profile["interviewSummary"] == {"totalCount": 1, "averageScore": 80}
    home = (await client.get("/api/me/home")).json()
    assert home["analysisStatus"] == "completed"
    assert home["analysis"]["roleSummary"] == "Stored summary"
    assert [item["id"] for item in home["recentInterviews"]] == [str(mine.id)]


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
