"""면접 생성 검사 쿼리. spec/backend/features/interview.md "생성 검사 해석".

docs/testing.md Interview create / task-13
"""

import itertools
import uuid
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    AnalysisJob,
    AnalysisRepoCandidate,
    InterviewSession,
    JobPosting,
    RepoAnalysis,
    Repository,
    User,
)
from app.features.interview import queries

_seq = itertools.count(1)


async def _user(db: AsyncSession) -> User:
    user = User(name="tester")
    db.add(user)
    await db.flush()
    return user


async def _run(db: AsyncSession, user: User, **overrides: Any) -> AnalysisJob:
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


async def _repo(
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


@pytest.mark.parametrize("status", ["succeeded", "partial"])
async def test_current_run_ok(db: AsyncSession, status: str) -> None:
    user = await _user(db)
    run = await _run(db, user, status=status)
    assert await queries.get_current_run(db, user_id=user.id, run_id=run.id) == run


@pytest.mark.parametrize(
    "overrides",
    [
        {"status": "running"},
        {"status": "failed"},
        {"job_type": "initial_sync"},
        {"job_posting_id": None},
    ],
)
async def test_current_run_rejected(db: AsyncSession, overrides: dict[str, Any]) -> None:
    user = await _user(db)
    run = await _run(db, user, **overrides)
    assert await queries.get_current_run(db, user_id=user.id, run_id=run.id) is None


async def test_current_run_other_user(db: AsyncSession) -> None:
    run = await _run(db, await _user(db))
    other = await _user(db)
    assert await queries.get_current_run(db, user_id=other.id, run_id=run.id) is None


@pytest.mark.parametrize(
    "repo_kwargs",
    [
        {"filter_status": "excluded"},
        {"is_private": True},
        {"is_accessible": False},
        {"l1_status": None},
        {"l1_status": "partial"},
        {"level": "l2"},
        {"in_run": False},
    ],
)
async def test_selectable_filters_out(db: AsyncSession, repo_kwargs: dict[str, Any]) -> None:
    run = await _run(db, await _user(db))
    ok = await _repo(db, run)
    bad = await _repo(db, run, **repo_kwargs)
    selectable = await queries.select_selectable_repository_ids(
        db, run_id=run.id, repository_ids=[ok.id, bad.id]
    )
    assert selectable == {ok.id}


async def test_selectable_other_run_candidate(db: AsyncSession) -> None:
    user = await _user(db)
    run, other_run = await _run(db, user), await _run(db, user)
    repo = await _repo(db, other_run)
    assert (
        await queries.select_selectable_repository_ids(db, run_id=run.id, repository_ids=[repo.id])
        == set()
    )


@pytest.mark.parametrize(
    ("status", "expected"),
    [("preparing", True), ("in_progress", True), ("completed", False), ("abandoned", False)],
)
async def test_has_active_interview(db: AsyncSession, status: str, expected: bool) -> None:
    run = await _run(db, await _user(db))
    assert await queries.has_active_interview(db, run_id=run.id) is False
    db.add(
        InterviewSession(
            user_id=run.user_id,
            analysis_job_id=run.id,
            job_posting_id=run.job_posting_id,
            status=status,
        )
    )
    await db.flush()
    assert await queries.has_active_interview(db, run_id=run.id) is expected
