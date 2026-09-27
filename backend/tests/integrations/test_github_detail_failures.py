"""GitHub 제한 대기와 저장소 접근 불가 증거의 회귀 검증."""

from unittest import mock

import httpx
import pytest

from app.integrations.github.base import GITHUB_ERROR_RATE_LIMITED, RepoSummary
from app.integrations.github.client import GithubClient

REPO = RepoSummary(github_repo_id=1, name="repo", full_name="user/repo", default_branch="main")


@pytest.mark.parametrize(
    ("headers", "expected_seconds"),
    [
        ({}, 60),
        ({"x-ratelimit-remaining": "4990", "x-ratelimit-reset": "1001"}, 60),
        ({"x-ratelimit-remaining": "4990", "x-ratelimit-reset": "5000"}, 60),
        ({"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1042"}, 42),
        ({"x-ratelimit-remaining": "0", "x-ratelimit-reset": "invalid"}, 60),
        ({"retry-after": "invalid"}, 60),
        ({"retry-after": "90", "x-ratelimit-reset": "1001"}, 90),
    ],
)
async def test_rate_limit_wait_uses_the_applicable_limit(
    headers: dict[str, str], expected_seconds: int
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403, headers=headers, json={"message": "You have exceeded a secondary rate limit"}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with mock.patch("app.integrations.github.client.time.time", return_value=1000):
            detail = await GithubClient("tok", client=http).fetch_repo_detail(REPO)

    assert detail.errors == [GITHUB_ERROR_RATE_LIMITED]
    assert detail.rate_limit_retry_after_seconds == expected_seconds


@pytest.mark.parametrize("status", [404, 503, None])
async def test_repository_access_requires_a_repository_level_not_found(status: int | None) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if status is None:
            raise httpx.ConnectTimeout("timeout", request=request)
        return httpx.Response(status)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        detail = await GithubClient("tok", client=http).fetch_repo_detail(REPO, login="user")

    assert detail.repository_inaccessible is (status == 404)
    assert detail.is_partial is True


@pytest.mark.parametrize("missing_path", ["/readme", "/commits/main"])
async def test_missing_readme_or_branch_does_not_prove_repository_is_inaccessible(
    missing_path: str,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith(missing_path):
            return httpx.Response(404)
        if request.url.path.endswith("/languages"):
            return httpx.Response(200, json={})
        return httpx.Response(503)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        detail = await GithubClient("tok", client=http).fetch_repo_detail(REPO)

    assert detail.repository_inaccessible is False


async def test_successful_commit_page_proves_access_even_when_total_is_unknown() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/commits"):
            return httpx.Response(
                200,
                json=[{"sha": "a" * 40}],
                headers={
                    "link": '<https://api.github.com/repos/user/repo/commits?page=2>; rel="next"'
                },
            )
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        detail = await GithubClient("tok", client=http).fetch_repo_detail(REPO)

    assert detail.commit_count is None
    assert detail.repository_inaccessible is False


@pytest.mark.parametrize("available_path", ["/readme", "/commits/main", "/commits"])
async def test_successful_data_overrides_an_inconsistent_languages_404(available_path: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith(available_path):
            if available_path == "/readme":
                return httpx.Response(200, json={"content": "# README", "encoding": "utf-8"})
            if available_path == "/commits/main":
                return httpx.Response(200, json={"sha": "a" * 40})
            return httpx.Response(409)
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        detail = await GithubClient("tok", client=http).fetch_repo_detail(REPO)

    # 빈 저장소의 commit_count=0도 접근 가능한 저장소라는 증거다.
    assert detail.repository_inaccessible is False
