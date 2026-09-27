"""step 3 · L0-b 추가 매핑. 후보 레포만 fetch_level='detail' 로 승격.
languages / README / 기본 브랜치 head SHA / 전체·사용자 커밋 수를 수집한다.

확정본 §2 M2 비용 최적화 / task-08
"""

from collections.abc import Awaitable, Callable

from app.integrations.github.base import (
    GITHUB_ERROR_RATE_LIMITED,
    GITHUB_ERROR_TOKEN_INVALID,
    RepoDetail,
    RepoSummary,
)
from app.integrations.github.client import DEFAULT_README_MAX_CHARS, GithubClient

# 입력: rate limit 이 풀릴 때까지 남은 초. `gh:rl:{githubUserId}` Redis 키 TTL 로 쓴다.
RateLimitRecorder = Callable[[int], Awaitable[None]]


async def collect_repo_details(
    client: GithubClient,
    repos: list[RepoSummary],
    *,
    login: str | None = None,
    readme_max_chars: int = DEFAULT_README_MAX_CHARS,
    on_rate_limited: RateLimitRecorder | None = None,
) -> dict[str, RepoDetail]:
    """후보 레포만 L0-b 로 승격한다.

    입력: GithubClient, 후보 RepoSummary 목록(repo_select 결과), 사용자 login,
          README 길이 상한, rate limit 감지 시 호출할 콜백.
    출력: {full_name: RepoDetail}.

    rate_limited 또는 token_invalid를 만나면 이후 레포 호출을 중단한다.
    이미 수집한 결과를 보존하고 호출하지 못한 레포에는 중단 원인을 그대로 남긴다.
    토큰 폐기 상태 저장과 run의 partial/failed 판정은 호출부가 맡는다.
    """
    results: dict[str, RepoDetail] = {}
    stopped_at: int | None = None
    stop_error: str | None = None

    for index, repo in enumerate(repos):
        detail = await client.fetch_repo_detail(
            repo, login=login, readme_max_chars=readme_max_chars
        )
        results[repo.full_name] = detail
        if GITHUB_ERROR_RATE_LIMITED in detail.errors:
            stop_error = GITHUB_ERROR_RATE_LIMITED
            if on_rate_limited and detail.rate_limit_retry_after_seconds is not None:
                await on_rate_limited(detail.rate_limit_retry_after_seconds)
        elif GITHUB_ERROR_TOKEN_INVALID in detail.errors:
            # 무효 토큰은 다른 저장소에서도 사용할 수 없으므로 배치 전체를 멈춘다.
            stop_error = GITHUB_ERROR_TOKEN_INVALID
        if stop_error is not None:
            stopped_at = index
            break

    if stopped_at is not None and stop_error is not None:
        for repo in repos[stopped_at + 1 :]:
            results[repo.full_name] = RepoDetail(errors=[stop_error])

    return results
