"""repo_detail L0-b 수집 오케스트레이션 — rate limit 만나면 이후 레포 호출 중단 (task-08)."""

from unittest import mock

import httpx
import pytest

from app.features.analysis.pipeline.steps.repo_detail import collect_repo_details
from app.integrations.github.base import GITHUB_ERROR_RATE_LIMITED, RepoDetail, RepoSummary
from app.integrations.github.client import GithubClient


def _repo(name: str) -> RepoSummary:
    return RepoSummary(github_repo_id=1, name=name, full_name=f"user/{name}")


def _client(details: list[RepoDetail]) -> GithubClient:
    client = mock.create_autospec(GithubClient, instance=True)
    client.fetch_repo_detail = mock.AsyncMock(side_effect=details)
    return client


async def test_collects_detail_for_every_repo_when_no_rate_limit() -> None:
    repos = [_repo("a"), _repo("b")]
    details = [RepoDetail(languages={"Python": 1}), RepoDetail(languages={"Go": 2})]

    results = await collect_repo_details(_client(details), repos)

    assert results["user/a"].languages == {"Python": 1}
    assert results["user/b"].languages == {"Go": 2}


async def test_stops_calling_further_repos_after_rate_limit() -> None:
    repos = [_repo("a"), _repo("b"), _repo("c")]
    client = _client(
        [RepoDetail(errors=[GITHUB_ERROR_RATE_LIMITED], rate_limit_retry_after_seconds=30)]
    )

    results = await collect_repo_details(client, repos)

    assert client.fetch_repo_detail.await_count == 1
    assert results["user/a"].errors == [GITHUB_ERROR_RATE_LIMITED]
    # b, c 는 호출하지 못했지만 결과에서 빠지지 않는다 — rate_limited 로 채워 반환한다.
    assert results["user/b"].errors == [GITHUB_ERROR_RATE_LIMITED]
    assert results["user/c"].errors == [GITHUB_ERROR_RATE_LIMITED]


async def test_records_rate_limit_via_callback() -> None:
    repos = [_repo("a")]
    client = _client(
        [RepoDetail(errors=[GITHUB_ERROR_RATE_LIMITED], rate_limit_retry_after_seconds=42)]
    )
    recorded: list[int] = []

    async def on_rate_limited(retry_after_seconds: int) -> None:
        recorded.append(retry_after_seconds)

    await collect_repo_details(client, repos, on_rate_limited=on_rate_limited)

    assert recorded == [42]


async def test_partial_result_within_a_single_repo_does_not_stop_the_loop() -> None:
    """레포 하나 안에서 일부 필드만 실패(partial)한 건 rate limit 이 아니면 계속 진행한다."""
    repos = [_repo("a"), _repo("b")]
    details = [
        RepoDetail(languages={}, errors=["no_readme"]),
        RepoDetail(languages={"Python": 1}),
    ]

    results = await collect_repo_details(_client(details), repos)

    assert results["user/a"].errors == ["no_readme"]
    assert results["user/b"].languages == {"Python": 1}


@pytest.mark.parametrize("has_callback", [True, False])
async def test_missing_retry_after_does_not_crash_callback_handling(has_callback: bool) -> None:
    repos = [_repo("a"), _repo("b")]
    client = _client([RepoDetail(errors=[GITHUB_ERROR_RATE_LIMITED])])
    recorded: list[int] = []

    async def on_rate_limited(retry_after_seconds: int) -> None:
        recorded.append(retry_after_seconds)

    await collect_repo_details(
        client, repos, on_rate_limited=on_rate_limited if has_callback else None
    )

    assert recorded == []


async def test_token_invalid_stops_the_batch_and_preserves_collected_data() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        seen.append(path)
        if path.endswith("/languages") and "/c/" not in path:
            return httpx.Response(200, json={"Python": 42})
        if "/a/" in path:
            if path.endswith("/readme"):
                return httpx.Response(200, json={"content": "# A", "encoding": "utf-8"})
            return httpx.Response(200, json=[])
        return httpx.Response(401)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        results = await collect_repo_details(
            GithubClient("tok", client=http), [_repo("a"), _repo("b"), _repo("c")]
        )

    assert results["user/a"].errors == []
    assert results["user/a"].readme_text == "# A"
    assert results["user/b"].languages == {"Python": 42}
    assert results["user/b"].errors == ["token_invalid"]
    assert results["user/c"].errors == ["token_invalid"]
    assert seen == [
        "/repos/user/a/languages",
        "/repos/user/a/readme",
        "/repos/user/a/commits",
        "/repos/user/b/languages",
        "/repos/user/b/readme",
    ]


async def test_secondary_limit_without_retry_header_records_one_minute_wait() -> None:
    recorded: list[int] = []

    async def on_rate_limited(seconds: int) -> None:
        recorded.append(seconds)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"message": "You have exceeded a secondary rate limit"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        results = await collect_repo_details(
            GithubClient("tok", client=http),
            [_repo("a"), _repo("b")],
            on_rate_limited=on_rate_limited,
        )

    assert recorded == [60]
    assert results["user/b"].errors == ["rate_limited"]
