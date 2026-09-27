"""첫 배치의 출처별 상한, 중복 제거와 전체 후보 보존 경계."""

from datetime import UTC, datetime, timedelta

import pytest

from app.features.analysis.pipeline.steps.repo_select import (
    FILTER_STATUS_ELIGIBLE,
    SELECTION_PORTFOLIO_MENTIONED,
    select_candidates,
)
from app.integrations.github.base import RepoSummary

MIN_SIZE_KB = 50


def _repo(name: str, *, pushed_days_ago: int = 0, is_private: bool = False) -> RepoSummary:
    return RepoSummary(
        github_repo_id=hash(name) & 0xFFFF,
        name=name,
        full_name=f"user/{name}",
        primary_language="Python",
        size_kb=100,
        is_private=is_private,
        pushed_at=datetime(2026, 9, 27, tzinfo=UTC) - timedelta(days=pushed_days_ago),
    )


def test_first_batch_caps_each_source_and_preserves_remaining_candidates() -> None:
    selections = select_candidates(
        [_repo(f"r{i}", pushed_days_ago=i) for i in range(15)],
        portfolio_full_names={f"user/r{i}" for i in range(10, 15)},
        high_contribution_full_names=["user/r7", "user/r8", "user/r9"],
        min_size_kb=MIN_SIZE_KB,
    )
    batch = sorted((s for s in selections if s.batch_rank is not None), key=lambda s: s.batch_rank)

    assert len(selections) == 15
    assert [s.repo.name for s in batch] == [
        "r10",
        "r11",
        "r12",
        "r0",
        "r1",
        "r2",
        "r3",
        "r4",
        "r7",
        "r8",
    ]
    assert [s.selection_reason for s in batch] == (
        ["portfolio_mentioned"] * 3 + ["base_rank_top"] * 5 + ["high_contribution"] * 2
    )
    assert [s.batch_rank for s in batch] == list(range(1, 11))
    assert all(s.batch_no == 1 for s in batch)
    assert all(s.filter_status == FILTER_STATUS_ELIGIBLE for s in selections)


def test_first_batch_deduplicates_sources_without_inventing_replacements() -> None:
    selections = select_candidates(
        [_repo(f"r{i}", pushed_days_ago=i) for i in range(12)],
        portfolio_full_names={"user/r0", "user/r1", "user/r2", "user/missing"},
        high_contribution_full_names=["user/r1", "user/r1", "user/r9", "user/r10"],
        min_size_kb=MIN_SIZE_KB,
    )

    batch = [s for s in selections if s.batch_no == 1]
    assert [s.repo.name for s in batch] == ["r0", "r1", "r2", "r3", "r4", "r9"]
    assert batch[0].selection_reason == SELECTION_PORTFOLIO_MENTIONED
    assert batch[-1].selection_reason == "high_contribution"


def test_contribution_source_skips_excluded_and_unknown_repos() -> None:
    selections = select_candidates(
        [_repo(f"r{i}", pushed_days_ago=i) for i in range(8)] + [_repo("private", is_private=True)],
        high_contribution_full_names=["user/private", "user/missing", "user/r7", "user/r6"],
        min_size_kb=MIN_SIZE_KB,
    )

    contribution = [s for s in selections if s.selection_reason == "high_contribution"]
    assert [s.repo.name for s in contribution] == ["r6", "r7"]
    assert [s.batch_rank for s in contribution] == [7, 6]


@pytest.mark.parametrize("limit", [-1, 11])
def test_batch_limit_cannot_exceed_contract(limit: int) -> None:
    with pytest.raises(ValueError):
        select_candidates([_repo("ok")], min_size_kb=MIN_SIZE_KB, limit=limit)


@pytest.mark.parametrize("limit", [0, 2])
def test_smaller_batch_limit_does_not_discard_candidates(limit: int) -> None:
    selections = select_candidates(
        [_repo(f"r{i}", pushed_days_ago=i) for i in range(4)],
        portfolio_full_names={"user/r3"},
        min_size_kb=MIN_SIZE_KB,
        limit=limit,
    )
    assert len(selections) == 4
    assert sum(s.batch_no == 1 for s in selections) == limit
