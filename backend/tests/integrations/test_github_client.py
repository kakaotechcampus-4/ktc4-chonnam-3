"""GitHub REST 클라이언트 — 페이지네이션, L0-b 수집, 오류 매핑.

spec/backend/features/analysis-run.md / task-08

아래 응답 모양은 실제 토큰으로 GitHub API 를 호출해 확인했다 (2026-09-21).
확인한 것: /user/repos 의 14개 필드와 타입, Link 헤더 형식, ETag -> 304,
/languages 의 {언어: int}, /readme 의 encoding=base64, /commits/{branch} 의 sha,
/commits?per_page=1 의 rel='last', 잘못된 토큰 401, 없는 repo 404.
"""

import base64
from collections.abc import Callable

import httpx
import pytest

from app.integrations.github.base import (
    GITHUB_ERROR_NO_README,
    GITHUB_ERROR_RATE_LIMITED,
    GITHUB_ERROR_REPO_UNREACHABLE,
    GITHUB_ERROR_TOKEN_INVALID,
    GithubApiError,
    RepoSummary,
)
from app.integrations.github.client import GithubClient

Handler = Callable[[httpx.Request], httpx.Response]

REPO_PAGE_1 = [
    {
        "id": 1,
        "name": "devon-api",
        "full_name": "octocat/devon-api",
        "language": "Python",
        "size": 300,
        "default_branch": "main",
    }
]
REPO_PAGE_2 = [
    {
        "id": 2,
        "name": "devon-web",
        "full_name": "octocat/devon-web",
        "language": "TypeScript",
        "size": 80,
        "default_branch": "main",
    }
]
NEXT_LINK = (
    '<https://api.github.com/user/repos?page=2>; rel="next", '
    '<https://api.github.com/user/repos?page=2>; rel="last"'
)
README_BODY = {
    "encoding": "base64",
    "content": base64.b64encode("# DEVON\n면접 준비 서비스".encode()).decode(),
}

SAMPLE_REPO = RepoSummary(
    github_repo_id=1,
    name="devon-api",
    full_name="octocat/devon-api",
    primary_language="Python",
    size_kb=300,
    default_branch="main",
)


def _client(handler: Handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def full_handler(request: httpx.Request) -> httpx.Response:
    """정상 응답 한 벌."""
    path = request.url.path
    if path == "/user/repos":
        if request.url.params.get("page") is None:
            return httpx.Response(200, json=REPO_PAGE_1, headers={"link": NEXT_LINK})
        return httpx.Response(200, json=REPO_PAGE_2)
    if path.endswith("/languages"):
        return httpx.Response(200, json={"Python": 12000, "HTML": 300})
    if path.endswith("/readme"):
        return httpx.Response(200, json=README_BODY)
    if "/commits/main" in path:
        return httpx.Response(200, json={"sha": "a" * 40})
    if path.endswith("/commits"):
        count = 37 if request.url.params.get("author") else 412
        return httpx.Response(
            200, json=[{}], headers={"link": f'<https://x?per_page=1&page={count}>; rel="last"'}
        )
    return httpx.Response(404)


# ── 목록 ───────────────────────────────────────────────


async def test_list_repositories_follows_next_link() -> None:
    async with _client(full_handler) as client:
        repos = await GithubClient("tok", client=client).list_repositories()

    assert [repo.full_name for repo in repos] == ["octocat/devon-api", "octocat/devon-web"]


async def test_repository_query_excludes_private() -> None:
    """visibility=public 이 private 를 걸러내는 지점이다.

    실제 호출로 확인했다 — /user 의 public_repos 개수와 이 요청의 결과 개수가 같고
    private 은 한 건도 오지 않는다. 이 파라미터가 빠지면 private 가 섞여 들어온다.
    """
    seen: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(dict(request.url.params))
        return httpx.Response(200, json=[])

    async with _client(handler) as client:
        await GithubClient("tok", client=client).list_repositories()

    assert seen[0]["visibility"] == "public"
    assert seen[0]["affiliation"] == "owner"


async def test_authorization_header_is_sent() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("authorization", ""))
        return httpx.Response(200, json=[])

    async with _client(handler) as client:
        await GithubClient("secret-token", client=client).list_repositories()

    assert seen == ["Bearer secret-token"]


# ── L0-b ───────────────────────────────────────────────


async def test_fetch_repo_detail_collects_everything() -> None:
    async with _client(full_handler) as client:
        detail = await GithubClient("tok", client=client).fetch_repo_detail(
            SAMPLE_REPO, login="octocat"
        )

    assert detail.languages == {"Python": 12000, "HTML": 300}
    assert detail.readme_text is not None and "DEVON" in detail.readme_text
    assert detail.head_sha == "a" * 40
    assert detail.commit_count == 412
    assert detail.user_commit_count == 37
    assert detail.errors == []
    assert detail.is_partial is False


async def test_readme_is_truncated_at_limit() -> None:
    async with _client(full_handler) as client:
        text, truncated = await GithubClient("tok", client=client).fetch_readme(
            "octocat/devon-api", max_chars=5
        )

    assert truncated is True
    assert len(text) == 5


async def test_commit_count_uses_link_header_not_full_list() -> None:
    """per_page=1 로 한 건만 받고 rel='last' 를 읽는다."""
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url.params.get("per_page")))
        return httpx.Response(200, json=[{}], headers={"link": '<https://x?page=3097>; rel="last"'})

    async with _client(handler) as client:
        count = await GithubClient("tok", client=client).count_commits("octocat/devon-api")

    assert count == 3097
    assert seen == ["1"]


async def test_empty_repository_commit_count_is_zero() -> None:
    """커밋이 하나도 없는 레포는 409 를 준다. 실패가 아니라 0이다."""
    async with _client(lambda request: httpx.Response(409)) as client:
        count = await GithubClient("tok", client=client).count_commits("octocat/empty")

    assert count == 0


# ── 오류 매핑 ──────────────────────────────────────────


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (httpx.Response(401), GITHUB_ERROR_TOKEN_INVALID),
        (
            httpx.Response(403, headers={"x-ratelimit-remaining": "0"}),
            GITHUB_ERROR_RATE_LIMITED,
        ),
        (
            httpx.Response(429, headers={"x-ratelimit-remaining": "0"}),
            GITHUB_ERROR_RATE_LIMITED,
        ),
        (
            httpx.Response(403, headers={"x-ratelimit-remaining": "99"}),
            GITHUB_ERROR_REPO_UNREACHABLE,
        ),
        (httpx.Response(404), GITHUB_ERROR_REPO_UNREACHABLE),
        (httpx.Response(500), GITHUB_ERROR_REPO_UNREACHABLE),
    ],
)
async def test_status_is_mapped_to_error_code(response: httpx.Response, expected: str) -> None:
    async with _client(lambda request: response) as client:
        with pytest.raises(GithubApiError) as caught:
            await GithubClient("tok", client=client).fetch_languages("octocat/devon-api")

    assert caught.value.error_code == expected


async def test_network_failure_is_repo_unreachable() -> None:
    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timeout", request=request)

    async with _client(timeout) as client:
        with pytest.raises(GithubApiError) as caught:
            await GithubClient("tok", client=client).fetch_languages("octocat/devon-api")

    assert caught.value.error_code == GITHUB_ERROR_REPO_UNREACHABLE


async def test_missing_readme_is_no_readme() -> None:
    async with _client(lambda request: httpx.Response(404)) as client:
        with pytest.raises(GithubApiError) as caught:
            await GithubClient("tok", client=client).fetch_readme("octocat/devon-api")

    assert caught.value.error_code == GITHUB_ERROR_NO_README


async def test_partial_detail_keeps_what_it_got() -> None:
    """rate limit 이 걸려도 그때까지 받은 것은 버리지 않는다."""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/languages"):
            return httpx.Response(200, json={"Python": 10})
        if path.endswith("/readme"):
            return httpx.Response(403, headers={"x-ratelimit-remaining": "0"})
        if "/commits/main" in path:
            return httpx.Response(403, headers={"x-ratelimit-remaining": "0"})
        return httpx.Response(200, json=[{}], headers={"link": '<https://x?page=5>; rel="last"'})

    async with _client(handler) as client:
        detail = await GithubClient("tok", client=client).fetch_repo_detail(SAMPLE_REPO)

    assert detail.languages == {"Python": 10}
    assert detail.commit_count == 5
    assert detail.readme_text is None
    assert detail.errors == [GITHUB_ERROR_RATE_LIMITED, GITHUB_ERROR_RATE_LIMITED]
    assert detail.is_partial is True


async def test_token_invalid_propagates_from_detail() -> None:
    """401 은 repo 하나의 문제가 아니라 토큰 문제라 errors 에 쌓인다."""
    async with _client(lambda request: httpx.Response(401)) as client:
        detail = await GithubClient("tok", client=client).fetch_repo_detail(SAMPLE_REPO)

    assert GITHUB_ERROR_TOKEN_INVALID in detail.errors


async def test_etag_is_sent_as_if_none_match() -> None:
    seen: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("if-none-match"))
        return httpx.Response(304)

    async with _client(handler) as client:
        response = await GithubClient("tok", client=client).request("/user/repos", etag='W/"abc"')

    assert seen == ['W/"abc"']
    # 304 는 실패가 아니다. 호출부가 캐시를 쓴다.
    assert response.status_code == 304
