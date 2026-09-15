"""repo_select 룰 필터와 첫 batch 구성 (DB 없이 순수 함수만)."""

import uuid
from datetime import timedelta

from app.db.models.github import Repository
from app.features.analysis.pipeline.steps.repo_select import (
    MAX_PORTFOLIO_IN_FIRST_BATCH,
    _filter_reason,
    _first_batch,
    _score,
)
from app.shared.clock import now
from app.shared.enums import FilterReason

MIN_SIZE_KB = 50


def make_repo(
    full_name: str,
    *,
    language: str | None = "Python",
    size_kb: int = 500,
    is_fork: bool = False,
    is_archived: bool = False,
    is_private: bool = False,
    stars: int = 0,
    days_ago: int = 10,
) -> Repository:
    return Repository(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        github_repo_id=abs(hash(full_name)) % 10**9,
        full_name=full_name,
        name=full_name.split("/")[-1],
        description="desc",
        html_url=f"https://github.com/{full_name}",
        primary_language=language,
        topics=[],
        stars=stars,
        forks=0,
        size_kb=size_kb,
        is_private=is_private,
        is_fork=is_fork,
        is_archived=is_archived,
        repo_pushed_at=now() - timedelta(days=days_ago),
        readme_truncated=False,
        fetch_level="list",
    )


def test_filter_reasons_are_separated() -> None:
    assert _filter_reason(make_repo("u/ok"), MIN_SIZE_KB, False) is None
    assert _filter_reason(make_repo("u/f", is_fork=True), MIN_SIZE_KB, False) is FilterReason.FORK
    assert (
        _filter_reason(make_repo("u/a", is_archived=True), MIN_SIZE_KB, False)
        is FilterReason.ARCHIVED
    )
    assert (
        _filter_reason(make_repo("u/n", language=None), MIN_SIZE_KB, False)
        is FilterReason.NO_LANGUAGE
    )
    assert (
        _filter_reason(make_repo("u/s", size_kb=10), MIN_SIZE_KB, False) is FilterReason.TOO_SMALL
    )
    assert (
        _filter_reason(make_repo("u/p", is_private=True), MIN_SIZE_KB, False)
        is FilterReason.PRIVATE
    )


def test_portfolio_repo_bypasses_rule_filter_but_not_private() -> None:
    forked = make_repo("u/portfolio", is_fork=True, size_kb=1)
    assert _filter_reason(forked, MIN_SIZE_KB, True) is None
    private = make_repo("u/secret", is_private=True)
    assert _filter_reason(private, MIN_SIZE_KB, True) is FilterReason.PRIVATE


def test_portfolio_repo_scores_above_others() -> None:
    mentioned = {"u/portfolio"}
    portfolio = _score(make_repo("u/portfolio", days_ago=400), mentioned, MIN_SIZE_KB)
    fresh = _score(make_repo("u/fresh", days_ago=1, stars=50), mentioned, MIN_SIZE_KB)
    assert portfolio.score > fresh.score
    assert portfolio.portfolio_mentioned is True


def test_first_batch_caps_portfolio_and_fills_by_rank() -> None:
    mentioned = {f"u/p{i}" for i in range(5)}
    scored = sorted(
        [_score(make_repo(f"u/p{i}", days_ago=300), mentioned, MIN_SIZE_KB) for i in range(5)]
        + [_score(make_repo(f"u/r{i}", days_ago=i), set(), MIN_SIZE_KB) for i in range(12)],
        key=lambda item: (-item.score, item.repository.full_name),
    )
    batch = _first_batch([item for item in scored if item.eligible], 10)

    assert len(batch) == 10
    portfolio_in_batch = [item for item, _ in batch if item.portfolio_mentioned]
    assert len(portfolio_in_batch) == MAX_PORTFOLIO_IN_FIRST_BATCH
    assert len({item.repository.id for item, _ in batch}) == 10

    reasons = [str(reason) for _, reason in batch]
    assert reasons[:3] == ["portfolio_mentioned"] * 3
    # 포폴 다음 5개는 base_rank_top, 남는 자리는 other 로 채운다.
    assert reasons[3:8] == ["base_rank_top"] * 5
    assert reasons[8:] == ["other"] * 2
