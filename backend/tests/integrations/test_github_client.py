"""GitHub REST 클라이언트 — 페이지네이션, L0-b 수집, 오류 매핑.

spec/backend/features/analysis-run.md / task-08

아래 응답 모양은 실제 토큰으로 GitHub API 를 호출해 확인했다 (2026-09-21).
확인한 것: /user/repos 의 14개 필드와 타입, Link 헤더 형식, ETag -> 304,
/languages 의 {언어: int}, /readme 의 encoding=base64, /commits/{branch} 의 sha,
/commits?per_page=1 의 rel='last', 잘못된 토큰 401, 없는 repo 404.
"""

import base64
from collections.abc import Callable
from unittest import mock

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
        "private": False,
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
        "private": False,
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


def _repo(repo_id: int, **overrides: object) -> dict[str, object]:
    """목록 API 가 항상 주는 필수 필드만 갖춘 repo 한 건."""
    return {
        "id": repo_id,
        "name": f"repo-{repo_id}",
        "full_name": f"octocat/repo-{repo_id}",
        "private": False,
        **overrides,
    }


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


async def test_truncated_readme_marks_detail_as_partial() -> None:
    """README 축약은 errors 에 안 남지만 완전한 수집이 아니라 is_partial=True 여야 한다."""
    async with _client(full_handler) as client:
        detail = await GithubClient("tok", client=client).fetch_repo_detail(
            SAMPLE_REPO, readme_max_chars=5
        )

    assert detail.readme_truncated is True
    assert detail.errors == []
    assert detail.is_partial is True


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
        (
            # secondary rate limit: remaining 은 남아 있어도 Retry-After 로 알려준다.
            httpx.Response(403, headers={"x-ratelimit-remaining": "4990", "retry-after": "60"}),
            GITHUB_ERROR_RATE_LIMITED,
        ),
        (
            # secondary rate limit: Retry-After 도 없이 본문 메시지로만 알려주는 경우.
            httpx.Response(
                403,
                headers={"x-ratelimit-remaining": "4990"},
                json={"message": "You have exceeded a secondary rate limit"},
            ),
            GITHUB_ERROR_RATE_LIMITED,
        ),
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


async def test_partial_detail_keeps_what_it_got_before_rate_limit() -> None:
    """rate limit 이 걸리기 전까지 받은 것은 버리지 않는다.

    ★ languages(성공) 다음 readme 에서 rate limit 을 맞으면, 그 뒤 head_sha/commit_count 는
    아예 호출하지 않는다(수정된 동작) — 어차피 다 실패할 걸 알면서 GitHub 을 더 때리지 않는다.
    """
    seen_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        seen_paths.append(path)
        if path.endswith("/languages"):
            return httpx.Response(200, json={"Python": 10})
        if path.endswith("/readme"):
            return httpx.Response(403, headers={"x-ratelimit-remaining": "0"})
        return httpx.Response(200, json=[{}], headers={"link": '<https://x?page=5>; rel="last"'})

    async with _client(handler) as client:
        detail = await GithubClient("tok", client=client).fetch_repo_detail(SAMPLE_REPO)

    assert detail.languages == {"Python": 10}
    assert detail.readme_text is None
    assert detail.head_sha is None
    assert detail.commit_count is None
    assert detail.errors == [GITHUB_ERROR_RATE_LIMITED]
    assert detail.is_partial is True
    # commits 엔드포인트는 한 번도 호출되지 않아야 한다(중단 확인).
    assert not any("/commits" in path for path in seen_paths)


async def test_token_invalid_also_stops_subsequent_field_calls() -> None:
    """401 도 rate limit 과 마찬가지로 레포 하나의 문제가 아니라 즉시 중단해야 한다."""
    call_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        return httpx.Response(401)

    async with _client(handler) as client:
        detail = await GithubClient("tok", client=client).fetch_repo_detail(
            SAMPLE_REPO, login="octocat"
        )

    assert detail.errors == [GITHUB_ERROR_TOKEN_INVALID]
    assert call_count["n"] == 1


async def test_partial_detail_carries_retry_after_seconds() -> None:
    """rate limit 이면 x-ratelimit-reset 에서 남은 초를 계산해 detail 에 싣는다."""
    reset_epoch = 1_900_000_000

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/languages"):
            return httpx.Response(
                403,
                headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": str(reset_epoch)},
            )
        return httpx.Response(200, json={})

    async with _client(handler) as client:
        with mock.patch("app.integrations.github.client.time.time", return_value=reset_epoch - 42):
            detail = await GithubClient("tok", client=client).fetch_repo_detail(SAMPLE_REPO)

    assert detail.rate_limit_retry_after_seconds == 42


async def test_missing_reset_still_provides_a_safe_rate_limit_wait() -> None:
    async with _client(
        lambda request: httpx.Response(403, headers={"x-ratelimit-remaining": "0"})
    ) as client:
        with pytest.raises(GithubApiError) as caught:
            await GithubClient("tok", client=client).fetch_languages("octocat/devon-api")

    assert caught.value.retry_after_seconds == 60


async def test_retry_after_header_wins_over_ratelimit_reset() -> None:
    """secondary rate limit 은 reset epoch 를 안 줄 수 있어 Retry-After 를 먼저 본다."""
    async with _client(
        lambda request: httpx.Response(
            403, headers={"retry-after": "90", "x-ratelimit-reset": "9999999999"}
        )
    ) as client:
        with pytest.raises(GithubApiError) as caught:
            await GithubClient("tok", client=client).fetch_languages("octocat/devon-api")

    assert caught.value.retry_after_seconds == 90


async def test_follows_redirect_and_parses_final_response() -> None:
    """리디렉션 안내 본문을 데이터로 파싱하지 않고 최종 응답을 따라가 파싱한다."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/repos/octocat/renamed-repo/languages":
            return httpx.Response(
                301, headers={"location": "https://api.github.com/repositories/999/languages"}
            )
        if request.url.path == "/repositories/999/languages":
            return httpx.Response(200, json={"Python": 42})
        return httpx.Response(404)

    async with _client(handler) as client:
        languages = await GithubClient("tok", client=client).fetch_languages("octocat/renamed-repo")

    assert languages == {"Python": 42}


async def test_cross_host_redirect_does_not_forward_token() -> None:
    """repo 상세 호출은 redirect 를 따라가지만, 다른 호스트로 가면 httpx 가 토큰을 제거한다."""
    auth_by_host: dict[str, str | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        auth_by_host[request.url.host] = request.headers.get("authorization")
        if request.url.host == "api.github.com":
            return httpx.Response(301, headers={"location": "https://other.example/languages"})
        return httpx.Response(200, json={"Python": 1})

    async with _client(handler) as client:
        await GithubClient("secret-token", client=client).fetch_languages("octocat/devon-api")

    assert auth_by_host == {"api.github.com": "Bearer secret-token", "other.example": None}


async def test_list_deduplicates_repo_moved_between_pages_keeping_order_and_latest() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("page") == "2":
            repos = [
                _repo(1, description="newer"),
                _repo(3),
            ]
            return httpx.Response(200, json=repos)
        return httpx.Response(
            200,
            json=[_repo(1, description="older"), _repo(2)],
            headers={"link": '<https://api.github.com/user/repos?page=2>; rel="next"'},
        )

    async with _client(handler) as client:
        repos = await GithubClient("tok", client=client).list_repositories()

    assert [repo.github_repo_id for repo in repos] == [1, 2, 3]
    assert repos[0].description == "newer"


async def test_list_fails_instead_of_returning_partial_result_when_later_page_is_invalid() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("page") == "2":
            return httpx.Response(200, json={"message": "unexpected"})
        return httpx.Response(
            200,
            json=[_repo(1)],
            headers={"link": '<https://api.github.com/user/repos?page=2>; rel="next"'},
        )

    async with _client(handler) as client:
        with pytest.raises(GithubApiError) as caught:
            await GithubClient("tok", client=client).list_repositories()

    assert caught.value.error_code == GITHUB_ERROR_REPO_UNREACHABLE


async def test_list_rejects_next_page_that_does_not_advance() -> None:
    """page 가 앞으로 가지 않는 next 는 순환이므로 두 번째 요청 없이 실패한다."""
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json=[_repo(1)],
            headers={"link": '<https://api.github.com/user/repos?page=1>; rel="next"'},
        )

    async with _client(handler) as client:
        with pytest.raises(GithubApiError):
            await GithubClient("tok", client=client).list_repositories()

    assert len(requests) == 1


async def test_rate_limited_429_without_headers_is_rate_limited() -> None:
    async with _client(lambda request: httpx.Response(429)) as client:
        with pytest.raises(GithubApiError) as caught:
            await GithubClient("tok", client=client).fetch_languages("octocat/devon-api")

    assert caught.value.error_code == GITHUB_ERROR_RATE_LIMITED
    assert caught.value.retry_after_seconds == 60


async def test_branch_name_is_url_encoded() -> None:
    """`#`/`/` 가 든 브랜치 이름이 fragment 로 잘리거나 다른 경로로 해석되지 않아야 한다.

    httpx.URL.path 는 표시할 때 percent-encoding 을 다시 풀어 보여준다 — 실제로 어떤
    bytes 가 나갔는지는 raw_path 로 확인해야 한다.
    """
    seen_raw_paths: list[bytes] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_raw_paths.append(request.url.raw_path)
        return httpx.Response(200, json={"sha": "b" * 40})

    async with _client(handler) as client:
        sha = await GithubClient("tok", client=client).fetch_head_sha(
            "octocat/devon-api", "release#v1"
        )

    assert sha == "b" * 40
    assert seen_raw_paths == [b"/repos/octocat/devon-api/commits/release%23v1"]


async def test_branch_name_with_special_characters_resolves_correct_branch() -> None:
    """인코딩 없이 나가면 `release#v1` 요청이 `release` 브랜치로 오인돼 다른 SHA 를 받는다."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.raw_path == b"/repos/octocat/devon-api/commits/release":
            return httpx.Response(200, json={"sha": "a" * 40})
        if request.url.raw_path == b"/repos/octocat/devon-api/commits/release%23v1":
            return httpx.Response(200, json={"sha": "b" * 40})
        return httpx.Response(404)

    async with _client(handler) as client:
        sha = await GithubClient("tok", client=client).fetch_head_sha(
            "octocat/devon-api", "release#v1"
        )

    assert sha == "b" * 40


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
