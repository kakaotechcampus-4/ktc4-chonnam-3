"""후보 저장의 소유권, 선택 근거, 순서와 재호출 경계를 검증한다."""

import asyncio
import importlib
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.errors import AppError
from app.db.models.analysis import AnalysisJob, AnalysisRepoCandidate
from app.db.models.github import Repository
from app.db.models.user import User

NOW = datetime(2026, 9, 28, tzinfo=UTC)


def _service():
    return importlib.import_module("app.features.analysis.candidates")


async def _seed(db, count=8):
    user = User(name="후보 저장 검증")
    db.add(user)
    await db.flush()
    run = AnalysisJob(user_id=user.id, job_type="analysis_run", status="queued")
    repos = [
        Repository(
            user_id=user.id,
            github_repo_id=index + 1,
            name=f"Project{index}",
            full_name=f"Owner/Project{index}",
            primary_language="Python",
            size_kb=100,
            pushed_at=NOW - timedelta(days=index),
            is_accessible=True,
            is_private=False,
            is_fork=False,
            is_archived=False,
        )
        for index in range(count)
    ]
    db.add_all([run, *repos])
    await db.flush()
    return run, repos


async def test_owned_exclusions_do_not_consume_accessible_batch_slots(db_session):
    run, repos = await _seed(db_session)
    repos[0].is_accessible = False
    repos[1].is_private = True
    repos[1].is_accessible = False
    repos[2].is_fork = True
    other = User(name="다른 사용자")
    db_session.add(other)
    await db_session.flush()
    db_session.add(
        Repository(user_id=other.id, github_repo_id=99, name="Other", full_name="Other/Repo")
    )
    await db_session.flush()

    rows = await _service().prepare_candidates(db_session, run.id, min_size_kb=50)

    assert [row.repository_id for row in rows] == [repo.id for repo in repos]
    assert [row.base_rank for row in rows] == list(range(1, 9))
    assert [row.filter_reason for row in rows[:3]] == ["inaccessible", "private", "fork"]
    assert [row.filter_status for row in rows[:3]] == ["excluded"] * 3
    batch = await _service().get_batch_candidates(db_session, run.id)
    assert [row.repository_id for row in batch] == [repo.id for repo in repos[3:]]
    assert [row.batch_rank for row in batch] == [1, 2, 3, 4, 5]
    assert rows[0].ranking_score == Decimal("100.000")
    assert rows[-1].ranking_score == Decimal("12.500")


async def test_casefold_portfolio_preserves_original_names_and_rule_evidence(db_session):
    run, repos = await _seed(db_session, 9)
    repos[7].is_fork = True
    rows = await _service().prepare_candidates(
        db_session,
        run.id,
        portfolio_full_names=["owner/project7", "OWNER/PROJECT7", "owner/project8", "missing/repo"],
        min_size_kb=50,
    )
    by_repo = {row.repository_id: row for row in rows}
    fork = by_repo[repos[7].id]
    assert fork.filter_status == "eligible"
    assert fork.selection_reason == "portfolio_mentioned"
    assert fork.ranking_signals["portfolio_mentioned"] is True
    assert fork.ranking_signals["rule_eligible"] is False
    assert by_repo[repos[8].id].ranking_signals["rule_eligible"] is True
    assert by_repo[repos[0].id].ranking_signals["portfolio_mentioned"] is False
    assert repos[7].full_name == "Owner/Project7"
    batch = await _service().get_batch_candidates(db_session, run.id)
    assert [row.repository_id for row in batch] == [repos[7].id, repos[8].id] + [
        repo.id for repo in repos[:5]
    ]
    remaining = await _service().get_remaining_candidates(db_session, run.id)
    assert [row.repository_id for row in remaining] == [repos[5].id, repos[6].id]


async def test_tied_and_missing_activity_have_stable_github_id_order(db_session):
    run, repos = await _seed(db_session, 4)
    for repo in repos[:3]:
        repo.pushed_at = NOW
    repos[3].pushed_at = None
    repos[0].github_repo_id, repos[2].github_repo_id = 30, 10
    repos[1].github_repo_id = 20
    await db_session.flush()

    rows = await _service().prepare_candidates(db_session, run.id, min_size_kb=50)

    assert [row.repository_id for row in rows] == [
        repos[2].id,
        repos[1].id,
        repos[0].id,
        repos[3].id,
    ]
    assert [row.ranking_score for row in rows] == [
        Decimal("100.000"),
        Decimal("75.000"),
        Decimal("50.000"),
        Decimal("25.000"),
    ]


async def test_existing_snapshot_and_unknown_signals_survive_repreparation(db_session):
    run, repos = await _seed(db_session, 7)
    first = await _service().prepare_candidates(db_session, run.id, min_size_kb=50)
    first[0].ranking_signals = {**first[0].ranking_signals, "analysis_id": "snapshot-marker"}
    ids = [row.id for row in first]
    repos[-1].pushed_at = NOW + timedelta(days=1)
    await db_session.flush()

    second = await _service().prepare_candidates(
        db_session, run.id, min_size_kb=999, portfolio_full_names=[repos[-1].full_name]
    )

    assert [row.id for row in second] == ids
    assert second[0].ranking_signals["analysis_id"] == "snapshot-marker"
    assert second[0].repository_id == repos[0].id


async def test_empty_result_can_be_reconsidered_after_repository_sync(db_session):
    run, _ = await _seed(db_session, 0)
    assert await _service().prepare_candidates(db_session, run.id, min_size_kb=50) == []
    db_session.add(
        Repository(
            user_id=run.user_id,
            github_repo_id=1,
            name="New",
            full_name="Owner/New",
            primary_language="Python",
            size_kb=100,
        )
    )
    await db_session.flush()
    assert len(await _service().prepare_candidates(db_session, run.id, min_size_kb=50)) == 1
    assert run.steps == []


async def test_contribution_requires_matching_fresh_and_persisted_counts(db_session):
    from app.integrations.github.base import RepoDetail

    run, repos = await _seed(db_session, 10)
    for repo in repos[5:]:
        repo.head_sha = "a" * 40
        repo.user_commit_count = 50
        repo.synced_at = NOW
    details = {
        "owner/project6": RepoDetail(head_sha="b" * 40, user_commit_count=50),
        "owner/project7": RepoDetail(head_sha="a" * 40, user_commit_count=49),
        "owner/project8": RepoDetail(head_sha="a" * 40, user_commit_count=50),
        "owner/project9": RepoDetail(head_sha="a" * 40, user_commit_count=50),
    }
    rows = await _service().prepare_candidates(
        db_session, run.id, min_size_kb=50, contribution_details=details
    )
    assert [row.repository_id for row in rows if row.selection_reason == "high_contribution"] == [
        repos[8].id,
        repos[9].id,
    ]
    assert all(row.batch_no is None for row in rows[5:8])


async def test_unverified_stored_counts_do_not_fill_contribution_slots(db_session):
    run, repos = await _seed(db_session)
    repos[-1].head_sha = "a" * 40
    repos[-1].user_commit_count = 500
    repos[-1].synced_at = NOW
    rows = await _service().prepare_candidates(db_session, run.id, min_size_kb=50)
    assert sum(row.batch_no == 1 for row in rows) == 5
    assert rows[-1].batch_no is None


@pytest.mark.parametrize(
    ("errors", "truncated", "inaccessible", "selected"),
    [
        (["no_readme"], False, False, True),
        (["repo_unreachable"], False, False, True),
        ([], True, False, True),
        (["rate_limited"], False, False, False),
        (["token_invalid"], False, False, False),
        ([], False, True, False),
    ],
)
async def test_contribution_uses_valid_field_evidence_without_ignoring_collection_stop(
    db_session, errors, truncated, inaccessible, selected
):
    from app.integrations.github.base import RepoDetail

    run, repos = await _seed(db_session, 6)
    repo = repos[-1]
    repo.head_sha = "a" * 40
    repo.user_commit_count = 50
    detail = RepoDetail(
        head_sha=repo.head_sha,
        user_commit_count=50,
        errors=errors,
        readme_truncated=truncated,
        repository_inaccessible=inaccessible,
    )
    rows = await _service().prepare_candidates(
        db_session, run.id, min_size_kb=50, contribution_details={repo.full_name: detail}
    )
    assert (rows[-1].selection_reason == "high_contribution") is selected
    if inaccessible:
        assert rows[-1].filter_reason == "inaccessible"


async def test_caller_can_roll_back_the_entire_candidate_snapshot(session_factory):
    async with session_factory() as db:
        run, _ = await _seed(db, 3)
        run_id = run.id
        await db.commit()
    async with session_factory() as db:
        rows = await _service().prepare_candidates(db, run_id, min_size_kb=50)
        assert [row.ranking_score for row in rows] == [
            Decimal("100.000"),
            Decimal("66.667"),
            Decimal("33.333"),
        ]
        await db.rollback()
    async with session_factory() as db:
        assert list(await db.scalars(select(AnalysisRepoCandidate))) == []


@pytest.mark.parametrize("job_type", [None, "initial_sync"])
async def test_only_existing_analysis_runs_can_prepare_candidates(db_session, job_type):
    run_id = uuid4()
    if job_type:
        run, _ = await _seed(db_session, 0)
        run.job_type = job_type
        await db_session.flush()
        run_id = run.id
    with pytest.raises(AppError) as caught:
        await _service().prepare_candidates(db_session, run_id, min_size_kb=50)
    assert caught.value.reason.value == "not_found"


async def test_concurrent_preparation_preserves_one_snapshot(session_factory):
    async with session_factory() as db:
        run, _ = await _seed(db, 8)
        run_id = run.id
        await db.commit()

    async def prepare():
        async with session_factory() as db:
            rows = await _service().prepare_candidates(db, run_id, min_size_kb=50)
            ids = [row.id for row in rows]
            await db.commit()
            return ids

    left, right = await asyncio.gather(prepare(), prepare())
    assert left == right
    async with session_factory() as db:
        rows = list(await db.scalars(select(AnalysisRepoCandidate)))
    assert len(rows) == 8
