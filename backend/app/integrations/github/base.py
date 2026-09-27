"""GitHub 수집 공통 타입과 룰 필터.

spec/backend/features/analysis-run.md / task-08

integrations 는 DB 를 모른다. 여기서는 API 응답을 구조화하고 제외 사유만 판정한다.
analysis_repo_candidates 행을 쓰는 것은 service 가 한다.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

# repo_analyses.error_code / analysis_jobs.error_code (docs/error-reasons.md)
GITHUB_ERROR_RATE_LIMITED = "rate_limited"
GITHUB_ERROR_REPO_UNREACHABLE = "repo_unreachable"
GITHUB_ERROR_TOKEN_INVALID = "token_invalid"
GITHUB_ERROR_NO_README = "no_readme"

# analysis_repo_candidates.filter_reason
FILTER_PRIVATE = "private"
FILTER_FORK = "fork"
FILTER_ARCHIVED = "archived"
FILTER_NO_LANGUAGE = "no_language"
FILTER_TOO_SMALL = "too_small"
FILTER_INACCESSIBLE = "inaccessible"


class GithubApiError(Exception):
    """GitHub 호출 실패.

    호출부가 repo 단위로 잡아 repo_analyses.error_code 에 적고 다음 repo 로 넘어간다.
    ★ token_invalid 를 받으면 호출부가 github_accounts.token_status='revoked' 로 UPDATE 하고
      이후 요청은 GitHub 호출 전에 차단한다. token_status 컬럼을 넣은 이유가 이 지점이다.
    """

    def __init__(
        self,
        error_code: str,
        *,
        status_code: int | None = None,
        retry_after_seconds: int | None = None,
    ) -> None:
        """입력: error_code, HTTP 상태코드(있으면), rate limit 해제까지 남은 초(있으면).

        retry_after_seconds 는 error_code == GITHUB_ERROR_RATE_LIMITED 일 때만 의미가 있다.
        호출부가 `gh:rl:{githubUserId}` Redis 키의 TTL 로 쓴다.
        """
        self.error_code = error_code
        self.status_code = status_code
        self.retry_after_seconds = retry_after_seconds
        super().__init__(error_code)


@dataclass(frozen=True, slots=True)
class RepoSummary:
    """L0-a metadata. 목록 API 한 건에서 바로 만든다."""

    github_repo_id: int
    name: str
    full_name: str
    description: str | None = None
    primary_language: str | None = None
    topics: list[str] = field(default_factory=list)
    stars: int = 0
    forks: int = 0
    size_kb: int = 0
    default_branch: str | None = None
    is_private: bool = False
    is_fork: bool = False
    is_archived: bool = False
    pushed_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class RepoDetail:
    """L0-b 수집분.

    일부만 실패해도 나머지는 살린다. 실패한 항목은 errors 에 error_code 로 남고,
    호출부가 이를 repo_analyses.status='partial' 판정에 쓴다.
    """

    languages: dict[str, int] = field(default_factory=dict)
    readme_text: str | None = None
    readme_truncated: bool = False
    head_sha: str | None = None
    commit_count: int | None = None
    user_commit_count: int | None = None
    errors: list[str] = field(default_factory=list)
    # rate_limited 가 하나라도 나면 그때의 남은 초. 여러 번 나도 가장 처음 값을 쓴다 —
    # 어차피 같은 rate limit window 안이라 reset 시각은 같다.
    rate_limit_retry_after_seconds: int | None = None
    # 저장소 단위 404의 증거만 전달한다. 일시적인 장애는 후보 제외 사유가 아니다.
    repository_inaccessible: bool = False

    @property
    def is_partial(self) -> bool:
        """errors 가 있거나 README 를 잘랐으면 partial 이다.

        task-08 명세는 긴 README 축약도 partial 로 요구한다 — errors 목록에는 안 남지만
        완전한 수집은 아니다.
        """
        return bool(self.errors) or self.readme_truncated


def _as_int(value: object, default: int = 0) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else default


def _as_datetime(value: object) -> datetime | None:
    """GitHub 의 ISO8601 문자열을 datetime 으로. 입력: 값. 출력: datetime 또는 None."""
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def repo_summary_from_api(payload: dict[str, Any]) -> RepoSummary:
    """목록 API 응답 한 건을 RepoSummary 로 만든다.

    입력: repo JSON. 출력: RepoSummary.
    """
    topics = payload.get("topics")
    return RepoSummary(
        github_repo_id=_as_int(payload.get("id")),
        name=str(payload.get("name") or ""),
        full_name=str(payload.get("full_name") or ""),
        description=payload.get("description") or None,
        primary_language=payload.get("language") or None,
        topics=[str(topic) for topic in topics] if isinstance(topics, list) else [],
        stars=_as_int(payload.get("stargazers_count")),
        forks=_as_int(payload.get("forks_count")),
        size_kb=_as_int(payload.get("size")),
        default_branch=payload.get("default_branch") or None,
        is_private=bool(payload.get("private")),
        is_fork=bool(payload.get("fork")),
        is_archived=bool(payload.get("archived")),
        pushed_at=_as_datetime(payload.get("pushed_at")),
    )


def filter_reason(repo: RepoSummary, *, min_size_kb: int) -> str | None:
    """L0-a 룰 필터. 입력: RepoSummary, 최소 크기. 출력: 제외 사유, 통과면 None.

    기본 필터는 public, non-fork, non-archived, primary language 있음이다.
    제외 repo 도 사유와 함께 저장하므로 bool 이 아니라 사유를 돌려준다.
    inaccessible 은 여기서 판정하지 않는다 — 실제 호출이 실패해야 알 수 있다.
    """
    if repo.is_private:
        return FILTER_PRIVATE
    if repo.is_fork:
        return FILTER_FORK
    if repo.is_archived:
        return FILTER_ARCHIVED
    if not repo.primary_language:
        return FILTER_NO_LANGUAGE
    if repo.size_kb < min_size_kb:
        return FILTER_TOO_SMALL
    return None
