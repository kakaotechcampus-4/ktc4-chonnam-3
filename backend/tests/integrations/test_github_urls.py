"""GitHub URL 정규화·추출.

spec/backend/features/documents.md "GitHub URL 정규화" / task-09
"""

import pytest

from app.integrations.extract.github_urls import (
    extract_github_full_names,
    normalize_github_url,
)

SUPPORTED = [
    ("https://github.com/owner/repo", "owner/repo"),
    ("http://github.com/owner/repo", "owner/repo"),
    ("github.com/owner/repo", "owner/repo"),
    ("https://www.github.com/owner/repo", "owner/repo"),
]

# issue, PR, commit, blob, tree 하위 URL 은 owner/repo 까지 접는다.
SUBPATHS = [
    "https://github.com/owner/repo/issues/12",
    "https://github.com/owner/repo/pull/3",
    "https://github.com/owner/repo/commit/0123456789abcdef",
    "https://github.com/owner/repo/blob/main/src/app.py",
    "https://github.com/owner/repo/tree/main/src",
]

# trailing slash, query, hash, .git 제거
NORMALIZED = [
    "https://github.com/owner/repo/",
    "https://github.com/owner/repo?tab=readme-ov-file",
    "https://github.com/owner/repo#installation",
    "https://github.com/owner/repo.git",
]

EXCLUDED = [
    "https://gist.github.com/owner/2f0a1b",
    "https://gitlab.com/owner/repo",
    "https://bitbucket.org/owner/repo",
    # URL 없이 owner/repo 텍스트만 있는 패턴은 제외한다.
    "owner/repo",
    # 레포가 아니라 프로필이다.
    "https://github.com/owner",
]


@pytest.mark.parametrize(("url", "expected"), SUPPORTED)
def test_supported_forms(url: str, expected: str) -> None:
    assert normalize_github_url(url) == expected


@pytest.mark.parametrize("url", SUBPATHS)
def test_subpath_is_folded_to_repo_root(url: str) -> None:
    assert normalize_github_url(url) == "owner/repo"


@pytest.mark.parametrize("url", NORMALIZED)
def test_slash_query_hash_and_git_suffix_are_stripped(url: str) -> None:
    assert normalize_github_url(url) == "owner/repo"


@pytest.mark.parametrize("url", EXCLUDED)
def test_excluded_forms_return_none(url: str) -> None:
    assert normalize_github_url(url) is None


def test_reserved_path_is_not_treated_as_owner() -> None:
    assert normalize_github_url("https://github.com/orgs/acme/repositories") is None
    assert normalize_github_url("https://github.com/settings/profile") is None


def test_extract_keeps_order_and_deduplicates() -> None:
    text = """
    주요 프로젝트: https://github.com/Alice/devon-api
    이슈: https://github.com/Alice/devon-api/issues/42
    프론트: github.com/Alice/devon-web.git
    """

    assert extract_github_full_names(text) == ["Alice/devon-api", "Alice/devon-web"]


def test_extract_deduplicates_ignoring_case() -> None:
    text = "https://github.com/Bob/cli-tool 와 https://github.com/BOB/CLI-TOOL"

    assert extract_github_full_names(text) == ["Bob/cli-tool"]


def test_extract_strips_trailing_punctuation_and_brackets() -> None:
    text = "문장 끝 https://github.com/Bob/cli-tool. 괄호 (https://github.com/Carol/site)."

    assert extract_github_full_names(text) == ["Bob/cli-tool", "Carol/site"]


def test_extract_skips_gist_and_other_hosts() -> None:
    text = """
    https://gist.github.com/Alice/deadbeef
    https://gitlab.com/Alice/other
    https://github.com/Alice/real-repo
    """

    assert extract_github_full_names(text) == ["Alice/real-repo"]


def test_extract_returns_empty_list_without_urls() -> None:
    assert extract_github_full_names("깃허브 링크가 없는 포트폴리오입니다.") == []
