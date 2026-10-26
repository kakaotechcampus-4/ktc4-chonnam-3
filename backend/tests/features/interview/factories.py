"""면접 테스트 데이터. 기본값은 면접 생성 검사를 통과하는 상태이고, 인자 하나로 어긋나게 만든다.
make_interview 이하는 interview_prep 이 끝난 상태를 대신 만든다 (턴 저장·조회용).

task-13 / task-15
"""

import itertools
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    AnalysisJob,
    AnalysisRepoCandidate,
    Evidence,
    InterviewSession,
    InterviewTurn,
    JobPosting,
    RepoAnalysis,
    Repository,
    SessionRepository,
    User,
)

_seq = itertools.count(1)


async def make_user(db: AsyncSession) -> User:
    user = User(name="tester")
    db.add(user)
    await db.flush()
    return user


async def make_run(db: AsyncSession, user: User, **overrides: Any) -> AnalysisJob:
    posting = JobPosting(
        normalized_url=f"https://www.wanted.co.kr/wd/{uuid.uuid4()}",
        raw_url="https://www.wanted.co.kr/wd/1",
        parse_status="succeeded",
    )
    db.add(posting)
    await db.flush()
    fields: dict[str, Any] = {
        "user_id": user.id,
        "job_type": "analysis_run",
        "status": "succeeded",
        "job_posting_id": posting.id,
    }
    run = AnalysisJob(**(fields | overrides))
    db.add(run)
    await db.flush()
    return run


async def make_repo(
    db: AsyncSession,
    run: AnalysisJob,
    *,
    filter_status: str = "eligible",
    l1_status: str | None = "succeeded",
    level: str = "l1",
    in_run: bool = True,
    **overrides: Any,
) -> Repository:
    """run 후보로 등록된 repo. 기본값은 선택 가능한 상태다."""
    github_id = next(_seq)
    repo = Repository(
        user_id=run.user_id,
        github_repo_id=github_id,
        name=f"r{github_id}",
        full_name=f"u/r{github_id}",
        **overrides,
    )
    db.add(repo)
    await db.flush()
    if in_run:
        db.add(
            AnalysisRepoCandidate(
                analysis_job_id=run.id,
                repository_id=repo.id,
                base_rank=github_id,
                filter_status=filter_status,
            )
        )
    if l1_status is not None:
        db.add(
            RepoAnalysis(
                repository_id=repo.id,
                analysis_level=level,
                head_sha="a" * 40,
                prompt_version="v1",
                model="test-model",
                status=l1_status,
            )
        )
    await db.flush()
    return repo


async def make_interview(
    db: AsyncSession, run: AnalysisJob, repos: list[Repository], **overrides: Any
) -> InterviewSession:
    """준비가 끝난 진행 중 면접. 첫 repo 가 primary 다."""
    fields: dict[str, Any] = {
        "user_id": run.user_id,
        "analysis_job_id": run.id,
        "job_posting_id": run.job_posting_id,
        "status": "in_progress",
        "started_at": datetime.now(UTC),
    }
    interview = InterviewSession(**(fields | overrides))
    db.add(interview)
    await db.flush()
    db.add_all(
        SessionRepository(
            interview_session_id=interview.id,
            repository_id=repo.id,
            is_primary=i == 0,
            display_order=i,
        )
        for i, repo in enumerate(repos)
    )
    await db.flush()
    return interview


async def make_evidence(
    db: AsyncSession, interview: InterviewSession, repo: Repository, **overrides: Any
) -> Evidence:
    """L2 notable_areas 를 전개한 사전 분석 근거 (tool_name=NULL)."""
    fields: dict[str, Any] = {
        "interview_session_id": interview.id,
        "repository_id": repo.id,
        "source_type": "file",
        "git_ref": "a" * 40,
        "path": "src/app.py",
        "snippet": "def main(): ...",
    }
    evidence = Evidence(**(fields | overrides))
    db.add(evidence)
    await db.flush()
    return evidence


async def make_turn(
    db: AsyncSession,
    interview: InterviewSession,
    turn_no: int,
    *,
    answered: bool = False,
    **overrides: Any,
) -> InterviewTurn:
    """질문까지 던진 턴. answered=True 면 답변도 채운다."""
    now = datetime.now(UTC)
    fields: dict[str, Any] = {
        "interview_session_id": interview.id,
        "turn_no": turn_no,
        "persona": "hr_manager",
        "status": "asked",
        "question_text": f"질문 {turn_no}",
        "asked_at": now,
    }
    if answered:
        fields |= {"status": "answered", "answer_text": f"답변 {turn_no}", "answered_at": now}
    turn = InterviewTurn(**(fields | overrides))
    db.add(turn)
    await db.flush()
    return turn
