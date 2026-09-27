"""repo_select 룰 필터 + 포폴 합집합 (task-08)."""

from datetime import UTC, datetime, timedelta

from app.features.analysis.pipeline.steps.repo_select import (
    FILTER_STATUS_ELIGIBLE,
    FILTER_STATUS_EXCLUDED,
    SELECTION_BASE_RANK_TOP,
    SELECTION_PORTFOLIO_MENTIONED,
    is_inaccessible,
    matched_portfolio_count,
    reclassify_inaccessible,
    select_candidates,
)
from app.integrations.github.base import (
    FILTER_INACCESSIBLE,
    GITHUB_ERROR_NO_README,
    GITHUB_ERROR_RATE_LIMITED,
    GITHUB_ERROR_REPO_UNREACHABLE,
    RepoDetail,
    RepoSummary,
)

MIN_SIZE_KB = 50


def _repo(
    name: str,
    *,
    pushed_days_ago: int = 0,
    is_fork: bool = False,
    is_archived: bool = False,
    is_private: bool = False,
    primary_language: str | None = "Python",
    size_kb: int = 100,
) -> RepoSummary:
    return RepoSummary(
        github_repo_id=hash(name) & 0xFFFF,
        name=name,
        full_name=f"user/{name}",
        primary_language=primary_language,
        size_kb=size_kb,
        is_private=is_private,
        is_fork=is_fork,
        is_archived=is_archived,
        pushed_at=datetime.now(UTC) - timedelta(days=pushed_days_ago),
    )


def test_rule_filter_passes_only_matching_repos() -> None:
    repos = [
        _repo("ok", pushed_days_ago=1),
        _repo("forked", pushed_days_ago=2, is_fork=True),
        _repo("archived", pushed_days_ago=3, is_archived=True),
        _repo("no_lang", pushed_days_ago=4, primary_language=None),
        _repo("too_small", pushed_days_ago=5, size_kb=10),
        _repo("private", pushed_days_ago=6, is_private=True),
    ]

    selections = select_candidates(repos, min_size_kb=MIN_SIZE_KB)

    by_name = {s.repo.name: s for s in selections}
    assert by_name["ok"].filter_status == FILTER_STATUS_ELIGIBLE
    assert by_name["ok"].selection_reason == SELECTION_BASE_RANK_TOP
    assert by_name["forked"].filter_status == FILTER_STATUS_EXCLUDED
    assert by_name["forked"].filter_reason == "fork"
    assert by_name["archived"].filter_reason == "archived"
    assert by_name["no_lang"].filter_reason == "no_language"
    assert by_name["too_small"].filter_reason == "too_small"
    assert by_name["private"].filter_reason == "private"


def test_rule_filter_passes_top_n_by_pushed_at_and_excludes_rest() -> None:
    repos = [_repo(f"r{i}", pushed_days_ago=i) for i in range(15)]

    selections = select_candidates(repos, min_size_kb=MIN_SIZE_KB, limit=10)

    eligible = [s for s in selections if s.filter_status == FILTER_STATUS_ELIGIBLE]
    assert len(eligible) == 10
    assert {s.repo.name for s in eligible} == {f"r{i}" for i in range(10)}
    # limit 을 넘겨 탈락한 r10..r14 는 반환에 아예 포함되지 않는다(초과분 excluded 기록 없음).
    assert {s.repo.name for s in selections} == {f"r{i}" for i in range(10)}


def test_portfolio_repo_bypasses_rule_filter() -> None:
    repos = [
        *[_repo(f"r{i}", pushed_days_ago=i) for i in range(10)],  # limit 을 가득 채운다
        _repo("side_project", pushed_days_ago=99, is_archived=True),
    ]

    selections = select_candidates(
        repos,
        portfolio_full_names={"user/side_project"},
        min_size_kb=MIN_SIZE_KB,
        limit=10,
    )

    side = next(s for s in selections if s.repo.name == "side_project")
    assert side.filter_status == FILTER_STATUS_ELIGIBLE
    assert side.filter_reason is None
    assert side.selection_reason == SELECTION_PORTFOLIO_MENTIONED
    # base_rank 는 조작하지 않는다 — pushed_at 기준 원래 순위(맨 마지막)를 유지한다.
    assert side.base_rank == 11


def test_base_rank_is_independent_of_filter_or_portfolio_result() -> None:
    repos = [_repo("newest", pushed_days_ago=0), _repo("oldest", pushed_days_ago=100)]

    selections = select_candidates(repos, min_size_kb=MIN_SIZE_KB)

    assert next(s for s in selections if s.repo.name == "newest").base_rank == 1
    assert next(s for s in selections if s.repo.name == "oldest").base_rank == 2


def test_repos_without_pushed_at_sort_last() -> None:
    dated = _repo("dated", pushed_days_ago=0)
    undated = RepoSummary(
        github_repo_id=1,
        name="undated",
        full_name="user/undated",
        primary_language="Python",
        size_kb=100,
        pushed_at=None,
    )

    selections = select_candidates([undated, dated], min_size_kb=MIN_SIZE_KB)

    assert selections[0].repo.name == "dated"
    assert selections[-1].repo.name == "undated"


def test_matched_portfolio_count_ignores_names_not_found() -> None:
    repos = [_repo("found", pushed_days_ago=0)]
    portfolio_names = {"user/found", "user/typo-or-deleted"}

    selections = select_candidates(
        repos, portfolio_full_names=portfolio_names, min_size_kb=MIN_SIZE_KB
    )

    found, total = matched_portfolio_count(selections, portfolio_names)
    assert (found, total) == (1, 2)


# ── inaccessible (task-08 완료 조건: 7번째 케이스) ─────────────────────────


def test_is_inaccessible_when_every_field_failed_with_repo_unreachable() -> None:
    detail = RepoDetail(errors=[GITHUB_ERROR_REPO_UNREACHABLE, GITHUB_ERROR_REPO_UNREACHABLE])
    assert is_inaccessible(detail) is True


def test_is_not_inaccessible_when_only_rate_limited() -> None:
    """아직 확인 못 했을 뿐이지 레포가 사라졌는지는 모른다."""
    detail = RepoDetail(errors=[GITHUB_ERROR_RATE_LIMITED], rate_limit_retry_after_seconds=30)
    assert is_inaccessible(detail) is False


def test_is_not_inaccessible_when_only_readme_missing() -> None:
    """레포는 있는데 README 만 없는 정상 케이스."""
    detail = RepoDetail(
        languages={"Python": 100},
        head_sha="a" * 40,
        commit_count=10,
        errors=[GITHUB_ERROR_NO_README],
    )
    assert is_inaccessible(detail) is False


def test_is_not_inaccessible_when_some_fields_succeeded() -> None:
    """일부만 실패한 partial 은 inaccessible 이 아니다 — 레포 자체는 접근 가능하다."""
    detail = RepoDetail(languages={"Python": 100}, errors=[GITHUB_ERROR_REPO_UNREACHABLE])
    assert is_inaccessible(detail) is False


def test_reclassify_downgrades_eligible_candidate_that_became_inaccessible() -> None:
    repo = _repo("gone")
    selections = select_candidates([repo], min_size_kb=MIN_SIZE_KB)
    details = {"user/gone": RepoDetail(errors=[GITHUB_ERROR_REPO_UNREACHABLE])}

    updated = reclassify_inaccessible(selections, details)

    assert len(updated) == 1
    assert updated[0].filter_status == FILTER_STATUS_EXCLUDED
    assert updated[0].filter_reason == FILTER_INACCESSIBLE
    assert updated[0].selection_reason is None
    # base_rank 는 원래 순위를 유지한다.
    assert updated[0].base_rank == selections[0].base_rank


def test_reclassify_leaves_healthy_candidate_untouched() -> None:
    repo = _repo("alive")
    selections = select_candidates([repo], min_size_kb=MIN_SIZE_KB)
    details = {"user/alive": RepoDetail(languages={"Python": 100})}

    updated = reclassify_inaccessible(selections, details)

    assert updated == selections


def test_reclassify_leaves_already_excluded_candidate_untouched() -> None:
    """rule filter 로 이미 excluded 된 후보는 repo_detail 대상이 아니라 건드리지 않는다."""
    repo = _repo("forked", is_fork=True)
    selections = select_candidates([repo], min_size_kb=MIN_SIZE_KB)
    assert selections[0].filter_status == FILTER_STATUS_EXCLUDED

    updated = reclassify_inaccessible(selections, {"user/forked": RepoDetail()})

    assert updated == selections


def test_reclassify_skips_repos_with_no_detail_result() -> None:
    """repo_detail 을 아예 부르지 못한(rate limit 로 스킵된) repo 는 그대로 둔다."""
    repo = _repo("skipped")
    selections = select_candidates([repo], min_size_kb=MIN_SIZE_KB)

    updated = reclassify_inaccessible(selections, {})

    assert updated == selections
