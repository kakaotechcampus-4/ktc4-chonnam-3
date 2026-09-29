"""인증용 목록 검증과 상세 수집이 같은 GitHub 계약을 사용하는지 확인한다."""

from dataclasses import asdict

import httpx
import pytest

from app.integrations.github.base import GithubApiError
from app.integrations.github.client import GithubClient


async def test_validated_list_record_is_serializable_and_usable_for_detail():
    def provider(request):
        if request.url.path == "/user/repos":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": 11,
                        "name": "visible",
                        "full_name": "user/visible",
                        "private": False,
                        "language": "Python",
                        "default_branch": "main",
                    }
                ],
            )
        if request.url.path.endswith("/languages"):
            return httpx.Response(200, json={"Python": 10})
        if request.url.path.endswith("/readme"):
            return httpx.Response(404)
        if request.url.path.endswith("/commits/main"):
            return httpx.Response(200, json={"sha": "a" * 40})
        return httpx.Response(200, json=[{"sha": "a" * 40}])

    async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as http:
        client = GithubClient("test-token", client=http)
        repos = await client.list_repositories()
        # DB 저장에 쓰는 직렬화와 상세 수집에 같은 목록 DTO를 넘긴다.
        values = asdict(repos[0])
        detail = await client.fetch_repo_detail(repos[0])
    assert values["github_repo_id"] == 11
    assert values["primary_language"] == "Python"
    assert "id" not in values
    assert detail.languages == {"Python": 10}
    assert detail.head_sha == "a" * 40
    assert detail.errors == ["no_readme"]


@pytest.mark.parametrize(
    ("status", "headers", "message", "wait"),
    [
        (403, {"x-ratelimit-remaining": "100"}, "Secondary rate limit exceeded", 60),
        (429, {}, "", 60),
        (403, {"retry-after": "27"}, "", 27),
    ],
)
async def test_listing_preserves_rate_limit_code_and_wait(status, headers, message, wait):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(status, json={"message": message}, headers=headers)
        )
    ) as http:
        with pytest.raises(GithubApiError) as caught:
            await GithubClient("test-token", client=http).list_repositories()
    assert caught.value.error_code == "rate_limited"
    assert caught.value.retry_after_seconds == wait


@pytest.mark.parametrize(
    "payload",
    [
        {},
        [None],
        [{}],
        [{"id": 1, "name": "repo", "full_name": "user/repo"}],
        [{"id": True, "name": "repo", "full_name": "user/repo", "private": False}],
        [{"id": 1, "name": "repo", "full_name": "user/repo", "private": "false"}],
        [{"id": 1, "name": "", "full_name": "user/repo", "private": False}],
    ],
)
async def test_invalid_repository_payload_is_failure_instead_of_empty_success(payload):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    ) as http:
        with pytest.raises(GithubApiError) as caught:
            await GithubClient("test-token", client=http).list_repositories()
    assert caught.value.error_code == "repo_unreachable"


@pytest.mark.parametrize(
    "next_url",
    [
        "https://attacker.invalid/user/repos",
        "http://api.github.com/user/repos",
        "https://api.github.com:8443/user/repos",
        "https://user@api.github.com/user/repos",
        "https://api.github.com/user",
        "https://api.github.com/user/repos",
    ],
)
async def test_invalid_or_cyclic_pagination_never_sends_a_second_request(next_url):
    requests = []

    def provider(request):
        requests.append(request)
        # 순환 보호가 빠진 선행 구현을 검사할 때 테스트 요청이 무한히 반복되지 않게 한다.
        assert len(requests) <= 2, "GitHub pagination did not stop"
        return httpx.Response(200, json=[], headers={"link": f'<{next_url}>; rel="next"'})

    async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as http:
        with pytest.raises(GithubApiError):
            await GithubClient("test-token", client=http).list_repositories()
    assert len(requests) == 1


async def test_listing_refuses_redirect_without_following_it():
    requests = []

    def provider(request):
        requests.append(request)
        return httpx.Response(302, headers={"location": "https://attacker.invalid/user/repos"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as http:
        with pytest.raises(GithubApiError):
            await GithubClient("test-token", client=http).list_repositories()
    assert len(requests) == 1
