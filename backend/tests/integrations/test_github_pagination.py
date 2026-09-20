"""Link 헤더 파서와 L0-a 룰 필터.

spec/backend/features/analysis-run.md / task-08
"""

import pytest

from app.integrations.github.base import (
    FILTER_ARCHIVED,
    FILTER_FORK,
    FILTER_NO_LANGUAGE,
    FILTER_PRIVATE,
    FILTER_TOO_SMALL,
    RepoSummary,
    filter_reason,
    repo_summary_from_api,
)
from app.integrations.github.pagination import (
    last_page,
    page_of,
    parse_link_header,
    total_from_per_page_one,
)

COMMITS_LINK = (
    '<https://api.github.com/repositories/1/commits?per_page=1&page=2>; rel="next", '
    '<https://api.github.com/repositories/1/commits?per_page=1&page=3097>; rel="last"'
)

REPO_PAYLOAD = {
    "id": 123,
    "name": "devon",
    "full_name": "octocat/devon",
    "description": "면접 준비 서비스",
    "language": "Python",
    "topics": ["fastapi", "llm"],
    "stargazers_count": 12,
    "forks_count": 3,
    "size": 540,
    "default_branch": "main",
    "private": False,
    "fork": False,
    "archived": False,
    "pushed_at": "2026-09-01T10:00:00Z",
}


# ── Link 헤더 ──────────────────────────────────────────


def test_parse_link_header() -> None:
    links = parse_link_header(COMMITS_LINK)

    assert set(links) == {"next", "last"}
    assert links["last"].endswith("page=3097")


def test_parse_link_header_without_header() -> None:
    assert parse_link_header(None) == {}
    assert parse_link_header("") == {}


def test_page_of() -> None:
    assert page_of("https://x/commits?per_page=1&page=42") == 42
    assert page_of("https://x/commits?per_page=1") is None
    assert page_of("https://x/commits?page=abc") is None


def test_last_page() -> None:
    assert last_page(COMMITS_LINK) == 3097


def test_last_page_is_none_when_only_next() -> None:
    """페이지가 1장뿐이면 GitHub 이 rel='last' 를 주지 않는다."""
    assert last_page('<https://x?page=2>; rel="next"') is None


def test_total_uses_last_page() -> None:
    """per_page=1 이면 마지막 page 번호가 곧 전체 개수다."""
    assert total_from_per_page_one(COMMITS_LINK, 1) == 3097


def test_total_falls_back_to_returned_items() -> None:
    assert total_from_per_page_one(None, 1) == 1


def test_total_is_zero_for_empty_repository() -> None:
    """커밋이 하나도 없으면 Link 도 없고 받은 항목도 0이다."""
    assert total_from_per_page_one(None, 0) == 0


# ── L0-a 파싱 ──────────────────────────────────────────


def test_repo_summary_from_api() -> None:
    repo = repo_summary_from_api(REPO_PAYLOAD)

    assert repo.github_repo_id == 123
    assert repo.full_name == "octocat/devon"
    assert repo.primary_language == "Python"
    assert repo.topics == ["fastapi", "llm"]
    assert repo.size_kb == 540
    assert repo.default_branch == "main"
    assert repo.pushed_at is not None


def test_repo_summary_survives_missing_fields() -> None:
    """응답이 비어도 파싱이 죽지 않아야 한다. 한 건 때문에 run 전체가 실패하면 안 된다."""
    repo = repo_summary_from_api({})

    assert repo.github_repo_id == 0
    assert repo.topics == []
    assert repo.pushed_at is None


def test_repo_summary_ignores_bad_types() -> None:
    repo = repo_summary_from_api({**REPO_PAYLOAD, "size": "큼", "topics": "fastapi"})

    assert repo.size_kb == 0
    assert repo.topics == []


# ── 룰 필터 ────────────────────────────────────────────


def test_eligible_repo_has_no_filter_reason() -> None:
    assert filter_reason(repo_summary_from_api(REPO_PAYLOAD), min_size_kb=50) is None


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"private": True}, FILTER_PRIVATE),
        ({"fork": True}, FILTER_FORK),
        ({"archived": True}, FILTER_ARCHIVED),
        ({"language": None}, FILTER_NO_LANGUAGE),
        ({"size": 10}, FILTER_TOO_SMALL),
    ],
)
def test_excluded_cases_are_separated(overrides: dict[str, object], expected: str) -> None:
    """제외 repo 도 사유와 함께 저장하므로 케이스가 각각 구분돼야 한다."""
    repo = repo_summary_from_api({**REPO_PAYLOAD, **overrides})

    assert filter_reason(repo, min_size_kb=50) == expected


def test_private_wins_over_other_reasons() -> None:
    """private 은 다른 사유보다 먼저 판정한다. Sprint 1 은 private 를 아예 다루지 않는다."""
    repo = repo_summary_from_api({**REPO_PAYLOAD, "private": True, "fork": True, "size": 1})

    assert filter_reason(repo, min_size_kb=50) == FILTER_PRIVATE


def test_size_threshold_is_configurable() -> None:
    repo = repo_summary_from_api({**REPO_PAYLOAD, "size": 100})

    assert filter_reason(repo, min_size_kb=50) is None
    assert filter_reason(repo, min_size_kb=200) == FILTER_TOO_SMALL


def test_filter_does_not_decide_inaccessible() -> None:
    """inaccessible 은 실제 호출이 실패해야 알 수 있어 룰 필터에서 판정하지 않는다."""
    repo = RepoSummary(github_repo_id=1, name="a", full_name="u/a", primary_language="Go")

    assert filter_reason(repo, min_size_kb=0) is None
