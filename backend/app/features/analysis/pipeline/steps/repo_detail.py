"""step 3 · L0-b 추가 매핑. 후보 레포만 fetch_level='detail' 로 승격.
레포당 4회 — languages / readme / commits?per_page=1 / commits?per_page=1&author={login}
★ head_sha 와 commit_count 를 따로 부르지 않는다: commits?per_page=1 의 body[0].sha 가
  head_sha, Link 헤더 rel='last' 의 page=N 이 commit_count.

확정본 §2 M2 비용 최적화 / task-08
"""

from collections.abc import Awaitable, Callable

from app.integrations.github.base import GITHUB_ERROR_RATE_LIMITED, RepoDetail, RepoSummary
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

    한 레포에서라도 rate limit 이 걸리면 그 뒤 레포는 호출하지 않는다 — 남은 quota 가
    0인 채로 GitHub 을 계속 때려봐야 전부 실패할 뿐이다. 그때까지 모은 결과는 버리지 않고,
    호출하지 못한 나머지는 rate_limited 로 채워 반환한다(호출부가 repo_analyses.status=
    'partial'/'failed' 판정에 그대로 쓸 수 있게).
    """
    results: dict[str, RepoDetail] = {}
    rate_limited_at: int | None = None

    for index, repo in enumerate(repos):
        detail = await client.fetch_repo_detail(
            repo, login=login, readme_max_chars=readme_max_chars
        )
        results[repo.full_name] = detail
        if GITHUB_ERROR_RATE_LIMITED in detail.errors:
            rate_limited_at = index
            if on_rate_limited and detail.rate_limit_retry_after_seconds is not None:
                await on_rate_limited(detail.rate_limit_retry_after_seconds)
            break

    if rate_limited_at is not None:
        for repo in repos[rate_limited_at + 1 :]:
            results[repo.full_name] = RepoDetail(errors=[GITHUB_ERROR_RATE_LIMITED])

    return results
