"""면접 테스트 데이터. 기본값은 면접 생성 검사를 통과하는 상태이고, 인자 하나로 어긋나게 만든다.

task-13
"""

import itertools
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    AnalysisJob,
    AnalysisRepoCandidate,
    JobPosting,
    RepoAnalysis,
    Repository,
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
