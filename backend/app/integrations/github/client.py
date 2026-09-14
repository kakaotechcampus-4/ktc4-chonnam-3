"""GitHub REST v3 — rate limit 판정 포함. DB 를 모른다.

401 을 받으면 호출부가 github_accounts.token_status='revoked' 로 UPDATE 하고,
이후 요청은 GitHub 호출 전에 차단한다. token_status 컬럼을 넣은 이유가 이 지점이다.

확정본 §2 error_code / task-08
"""

from dataclasses import dataclass
from types import TracebackType
from typing import Any, Self

import httpx

from app.core.config import get_settings
from app.integrations.github.pagination import total_count_from_single_page


class GithubError(RuntimeError):
    """GitHub 호출 실패 공통 타입."""


class GithubTokenInvalid(GithubError):
    """401. 호출부가 token_status='revoked' 로 내린다."""


class GithubRateLimited(GithubError):
    """403/429 + remaining=0. 가능한 결과는 저장하고 실패분만 rate_limited 로 기록한다."""

    def __init__(self, reset_at: int | None = None) -> None:
        super().__init__("github rate limit exceeded")
        self.reset_at = reset_at


class GithubNotFound(GithubError):
    """404. private/삭제/오타 — 정상 상황으로 다룬다."""


@dataclass(frozen=True)
class HeadCommitInfo:
    """`commits?per_page=1` 한 번으로 얻는 head_sha 와 commit_count."""

    head_sha: str | None
    commit_count: int


class GithubClient:
    """public repo 수집 전용 얇은 client. 토큰 값은 log 에 남기지 않는다."""

    def __init__(self, access_token: str, *, client: httpx.AsyncClient | None = None) -> None:
        settings = get_settings()
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=settings.github_api_base,
            timeout=settings.github_timeout_seconds,
        )
        self._headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def _get(
        self, path: str, *, params: dict[str, Any] | None = None, accept: str | None = None
    ) -> httpx.Response:
        headers = dict(self._headers)
        if accept:
            headers["Accept"] = accept
        try:
            response = await self._client.get(path, params=params, headers=headers)
        except httpx.HTTPError as exc:
            raise GithubError(f"github request failed: {path}") from exc
        if response.status_code == 401:
            raise GithubTokenInvalid(path)
        if response.status_code in (403, 429) and self._is_rate_limited(response):
            reset = response.headers.get("x-ratelimit-reset")
            raise GithubRateLimited(int(reset) if reset and reset.isdigit() else None)
        if response.status_code == 404:
            raise GithubNotFound(path)
        if response.status_code >= 400:
            raise GithubError(f"github {response.status_code} for {path}")
        return response

    @staticmethod
    def _is_rate_limited(response: httpx.Response) -> bool:
        if response.headers.get("x-ratelimit-remaining") == "0":
            return True
        return "rate limit" in response.text.lower()

    # ── L0-a ─────────────────────────────────────────────────────────
    async def list_public_repos(self, *, per_page: int = 100) -> list[dict[str, Any]]:
        """소유한 public repo 전체. 목록 응답에 이미 들어있는 필드만 쓴다."""
        repos: list[dict[str, Any]] = []
        page = 1
        while True:
            response = await self._get(
                "/user/repos",
                params={
                    "visibility": "public",
                    "affiliation": "owner",
                    "per_page": per_page,
                    "page": page,
                    "sort": "pushed",
                },
            )
            batch: list[dict[str, Any]] = response.json()
            repos.extend(batch)
            if len(batch) < per_page:
                return repos
            page += 1

    # ── L0-b ─────────────────────────────────────────────────────────
    async def get_languages(self, full_name: str) -> dict[str, int]:
        """{언어: byte 수}. 비율 계산은 호출부(BE 규칙)."""
        response = await self._get(f"/repos/{full_name}/languages")
        return dict(response.json())

    async def get_readme(self, full_name: str) -> str | None:
        """raw README. 없으면 None (no_readme 는 실패가 아니라 정보 부족이다)."""
        try:
            response = await self._get(
                f"/repos/{full_name}/readme", accept="application/vnd.github.raw"
            )
        except GithubNotFound:
            return None
        return response.text

    async def get_head_commit_info(self, full_name: str) -> HeadCommitInfo:
        """head_sha 와 commit_count 를 한 번에 얻는다 (Link rel='last' = 전체 커밋 수)."""
        response = await self._get(f"/repos/{full_name}/commits", params={"per_page": 1})
        items: list[dict[str, Any]] = response.json()
        head_sha = str(items[0]["sha"]) if items else None
        count = total_count_from_single_page(response.headers.get("link"), len(items))
        return HeadCommitInfo(head_sha=head_sha, commit_count=count)

    async def get_author_commit_count(self, full_name: str, login: str) -> int:
        """사용자 본인 커밋 수. 남의 레포/기여 없음이면 0."""
        try:
            response = await self._get(
                f"/repos/{full_name}/commits", params={"per_page": 1, "author": login}
            )
        except GithubNotFound:
            return 0
        items: list[dict[str, Any]] = response.json()
        return total_count_from_single_page(response.headers.get("link"), len(items))
