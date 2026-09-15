"""GitHub Link 헤더 파서와 GitHub URL 정규화."""

from app.integrations.extract.github_urls import extract_full_names, normalize_repo_url
from app.integrations.github.pagination import (
    last_page_number,
    parse_link_header,
    total_count_from_single_page,
)

LINK = (
    '<https://api.github.com/repos/o/r/commits?per_page=1&page=2>; rel="next", '
    '<https://api.github.com/repos/o/r/commits?per_page=1&page=142>; rel="last"'
)


def test_parse_link_header() -> None:
    parsed = parse_link_header(LINK)
    assert set(parsed) == {"next", "last"}
    assert last_page_number(LINK) == 142


def test_commit_count_uses_last_page() -> None:
    assert total_count_from_single_page(LINK, 1) == 142
    # 링크가 없으면 첫 페이지 항목 수가 곧 전체 개수다.
    assert total_count_from_single_page(None, 1) == 1
    assert total_count_from_single_page(None, 0) == 0


def test_extract_full_names_from_portfolio_text() -> None:
    text = (
        "포트폴리오: https://github.com/kim/project-a 와 "
        "github.com/kim/project-b.git, 그리고 https://github.com/kim (프로필)"
    )
    assert extract_full_names(text) == ["kim/project-a", "kim/project-b"]


def test_normalize_repo_url() -> None:
    assert normalize_repo_url("https://github.com/kim/project-a/tree/main") == "kim/project-a"
    assert normalize_repo_url("https://github.com/kim") is None
