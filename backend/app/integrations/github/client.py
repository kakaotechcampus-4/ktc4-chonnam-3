"""GitHub REST v3 — ETag 캐시, rate limit(gh:rl:{githubUserId}). DB 를 모른다.
★ 401 을 받으면 호출부가 github_accounts.token_status='revoked' 로 UPDATE 하고,
  이후 요청은 GitHub 호출 전에 차단한다. token_status 컬럼을 넣은 이유가 이 지점이다.

확정본 §2 error_code / task-08

ETag 값 자체는 여기서 보관하지 않는다. 조건부 요청(If-None-Match)만 지원하고
저장은 호출부(Redis)가 한다 — integrations 는 저장소를 모른다.

응답 모양은 실제 토큰으로 확인했다 (2026-09-21). topics 는 preview Accept 헤더 없이
기본으로 오고, /user/repos?visibility=public&affiliation=owner 는 private 를 주지 않는다.
401 응답에는 x-ratelimit-remaining 헤더가 없어 rate limit 분기보다 먼저 판정한다.
"""

import base64
import binascii
import time
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import quote

import httpx

from app.integrations.github.base import (
    GITHUB_ERROR_NO_README,
    GITHUB_ERROR_RATE_LIMITED,
    GITHUB_ERROR_REPO_UNREACHABLE,
    GITHUB_ERROR_TOKEN_INVALID,
    GithubApiError,
    RepoDetail,
    RepoSummary,
    repo_summary_from_api,
)
from app.integrations.github.pagination import parse_link_header, total_from_per_page_one

API_BASE = "https://api.github.com"
DEFAULT_TIMEOUT_SECONDS = 15.0
DEFAULT_PER_PAGE = 100
# README 길이 상한. 넘으면 잘라 저장하고 partial 로 표시한다.
DEFAULT_README_MAX_CHARS = 20000

_ACCEPT = "application/vnd.github+json"
_API_VERSION = "2022-11-28"


class GithubClient:
    """사용자 토큰으로 GitHub REST v3 를 호출한다.

    토큰은 문자열로만 받는다. 복호화와 token_status 갱신은 호출부 몫이다.
    """

    def __init__(
        self,
        token: str,
        *,
        client: httpx.AsyncClient | None = None,
        api_base: str = API_BASE,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        """입력: access token, 주입할 client(테스트용), API base, timeout. 출력: 없음."""
        self._token = token
        self._client = client
        self._api_base = api_base.rstrip("/")
        self._timeout_seconds = timeout_seconds

    # ── 요청 ────────────────────────────────────────────

    def _headers(self, etag: str | None = None) -> dict[str, str]:
        headers = {
            "Accept": _ACCEPT,
            "Authorization": f"Bearer {self._token}",
            "X-GitHub-Api-Version": _API_VERSION,
        }
        if etag:
            headers["If-None-Match"] = etag
        return headers

    async def request(
        self,
        path: str,
        *,
        params: dict[str, str | int] | None = None,
        etag: str | None = None,
    ) -> httpx.Response:
        """GitHub 을 한 번 호출한다.

        입력: 경로(또는 전체 URL), 쿼리, ETag. 출력: Response.
        실패는 GithubApiError 로 던진다. 304 는 성공으로 돌려준다 — 호출부가 캐시를 쓴다.
        """
        url = path if path.startswith("http") else f"{self._api_base}{path}"
        try:
            if self._client is not None:
                response = await self._client.get(
                    url, params=params, headers=self._headers(etag), follow_redirects=True
                )
            else:
                async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                    response = await client.get(
                        url, params=params, headers=self._headers(etag), follow_redirects=True
                    )
        except httpx.HTTPError as error:
            raise GithubApiError(GITHUB_ERROR_REPO_UNREACHABLE) from error

        self._raise_for_status(response)
        return response

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        """상태코드를 error_code 로 옮긴다. 입력: Response. 출력: 없음(실패면 예외)."""
        status = response.status_code
        if status < httpx.codes.BAD_REQUEST or status == httpx.codes.NOT_MODIFIED:
            return
        if status == httpx.codes.UNAUTHORIZED:
            # 호출부가 token_status='revoked' 로 바꾸고 이후 호출을 막는다.
            raise GithubApiError(GITHUB_ERROR_TOKEN_INVALID, status_code=status)
        if status in (httpx.codes.FORBIDDEN, httpx.codes.TOO_MANY_REQUESTS):
            if _is_rate_limited(response):
                raise GithubApiError(
                    GITHUB_ERROR_RATE_LIMITED,
                    status_code=status,
                    retry_after_seconds=_retry_after_seconds(response),
                )
            raise GithubApiError(GITHUB_ERROR_REPO_UNREACHABLE, status_code=status)
        raise GithubApiError(GITHUB_ERROR_REPO_UNREACHABLE, status_code=status)

    # ── L0-a ────────────────────────────────────────────

    async def list_repositories(self, *, per_page: int = DEFAULT_PER_PAGE) -> list[RepoSummary]:
        """인증 사용자의 public repo 를 모두 가져온다.

        입력: page 크기. 출력: RepoSummary 목록.
        private 은 애초에 요청하지 않는다 — Sprint 1 은 public 만 다룬다.
        """
        return [repo async for repo in self.iter_repositories(per_page=per_page)]

    async def iter_repositories(
        self, *, per_page: int = DEFAULT_PER_PAGE
    ) -> AsyncIterator[RepoSummary]:
        """public repo 를 page 단위로 흘려보낸다. 입력: page 크기. 출력: RepoSummary 스트림."""
        path: str | None = "/user/repos"
        params: dict[str, str | int] | None = {
            "visibility": "public",
            "affiliation": "owner",
            "per_page": per_page,
            "sort": "pushed",
        }
        while path is not None:
            response = await self.request(path, params=params)
            payload = response.json()
            if not isinstance(payload, list):
                return
            for item in payload:
                if isinstance(item, dict):
                    yield repo_summary_from_api(item)
            # 다음 page URL 에 쿼리가 이미 들어 있어 params 를 다시 붙이지 않는다.
            path = parse_link_header(response.headers.get("link")).get("next")
            params = None

    # ── L0-b ────────────────────────────────────────────

    async def fetch_languages(self, full_name: str) -> dict[str, int]:
        """언어별 바이트 수. 입력: owner/repo. 출력: {언어: 바이트}."""
        payload = (await self.request(f"/repos/{full_name}/languages")).json()
        if not isinstance(payload, dict):
            return {}
        return {str(key): value for key, value in payload.items() if isinstance(value, int)}

    async def fetch_readme(
        self, full_name: str, *, max_chars: int = DEFAULT_README_MAX_CHARS
    ) -> tuple[str, bool]:
        """README 본문. 입력: owner/repo, 길이 상한. 출력: (본문, 잘렸는지).

        README 가 없으면 GithubApiError(no_readme) 를 던진다.
        """
        try:
            payload = (await self.request(f"/repos/{full_name}/readme")).json()
        except GithubApiError as error:
            if error.status_code == httpx.codes.NOT_FOUND:
                raise GithubApiError(GITHUB_ERROR_NO_README, status_code=404) from error
            raise

        text = _decode_readme(payload)
        if text is None:
            raise GithubApiError(GITHUB_ERROR_NO_README)
        if max_chars > 0 and len(text) > max_chars:
            return text[:max_chars], True
        return text, False

    async def fetch_head_sha(self, full_name: str, branch: str) -> str | None:
        """기본 브랜치의 head commit SHA. 입력: owner/repo, 브랜치. 출력: SHA 또는 None.

        branch 를 URL 인코딩한다 — `release#v1` 처럼 `#`/`/` 가 든 이름을 그대로 넣으면
        fragment 로 잘리거나 다른 경로로 해석돼 엉뚱한 브랜치의 SHA 를 반환할 수 있다.
        """
        encoded_branch = quote(branch, safe="")
        payload = (await self.request(f"/repos/{full_name}/commits/{encoded_branch}")).json()
        if isinstance(payload, dict):
            sha = payload.get("sha")
            if isinstance(sha, str) and sha:
                return sha
        return None

    async def count_commits(self, full_name: str, *, author: str | None = None) -> int | None:
        """커밋 수. 입력: owner/repo, author(있으면 그 사람 커밋만). 출력: 개수, 확정 못 하면 None.

        per_page=1 로 한 건만 받고 Link rel='last' 의 page 번호를 읽는다.
        전체 커밋을 받지 않기 위한 방법이다.
        """
        params: dict[str, str | int] = {"per_page": 1}
        if author:
            params["author"] = author
        try:
            response = await self.request(f"/repos/{full_name}/commits", params=params)
        except GithubApiError as error:
            # 커밋이 하나도 없는 빈 레포는 409 를 준다. 실패가 아니라 0이다.
            if error.status_code == httpx.codes.CONFLICT:
                return 0
            raise

        payload = response.json()
        returned = len(payload) if isinstance(payload, list) else 0
        return total_from_per_page_one(response.headers.get("link"), returned)

    async def fetch_repo_detail(
        self,
        repo: RepoSummary,
        *,
        login: str | None = None,
        readme_max_chars: int = DEFAULT_README_MAX_CHARS,
    ) -> RepoDetail:
        """L0-b 를 모아 온다. 입력: RepoSummary, 사용자 login, README 상한. 출력: RepoDetail.

        항목 하나가 실패해도(no_readme 등) 나머지는 계속 시도하고 errors 에 error_code 를
        남긴다. 다만 rate_limited 나 token_invalid 는 레포 하나만의 문제가 아니라 이후
        호출도 전부 실패할 게 뻔하므로, 그 시점에서 남은 필드 호출을 중단하고 그때까지
        모은 데이터와 실패 정보를 그대로 돌려준다.
        """
        errors: list[str] = []
        languages: dict[str, int] = {}
        readme_text: str | None = None
        readme_truncated = False
        head_sha: str | None = None
        commit_count: int | None = None
        user_commit_count: int | None = None
        retry_after: int | None = None
        stopped = False
        repository_inaccessible = False

        def _record(error: GithubApiError) -> None:
            nonlocal retry_after, stopped
            errors.append(error.error_code)
            if error.retry_after_seconds is not None and retry_after is None:
                retry_after = error.retry_after_seconds
            if error.error_code in (GITHUB_ERROR_RATE_LIMITED, GITHUB_ERROR_TOKEN_INVALID):
                stopped = True

        if not stopped:
            try:
                languages = await self.fetch_languages(repo.full_name)
            except GithubApiError as error:
                # README·브랜치의 404와 달리 languages의 404는 저장소 접근 불가 증거다.
                repository_inaccessible = error.status_code == httpx.codes.NOT_FOUND
                _record(error)

        if not stopped:
            try:
                readme_text, readme_truncated = await self.fetch_readme(
                    repo.full_name, max_chars=readme_max_chars
                )
                repository_inaccessible = False
            except GithubApiError as error:
                _record(error)

        branch = repo.default_branch
        if not stopped and branch:
            try:
                head_sha = await self.fetch_head_sha(repo.full_name, branch)
                repository_inaccessible = False
            except GithubApiError as error:
                _record(error)

        if not stopped:
            try:
                commit_count = await self.count_commits(repo.full_name)
                # 총 개수가 미확정이어도 정상 페이지를 받았다면 저장소에는 접근한 것이다.
                repository_inaccessible = False
            except GithubApiError as error:
                _record(error)

        if not stopped and login:
            try:
                user_commit_count = await self.count_commits(repo.full_name, author=login)
                repository_inaccessible = False
            except GithubApiError as error:
                _record(error)

        return RepoDetail(
            languages=languages,
            readme_text=readme_text,
            readme_truncated=readme_truncated,
            head_sha=head_sha,
            commit_count=commit_count,
            user_commit_count=user_commit_count,
            errors=errors,
            rate_limit_retry_after_seconds=retry_after,
            repository_inaccessible=repository_inaccessible,
        )


def _is_rate_limited(response: httpx.Response) -> bool:
    """403/429 가 primary 든 secondary 든 rate limit 인지 판정한다.

    입력: Response. 출력: rate limit 여부.

    GitHub 는 secondary rate limit 이면 `x-ratelimit-remaining` 이 0 이 아니어도 403/429 를
    준다 — 대신 `Retry-After` 헤더나 본문 메시지("secondary rate limit")로 알려준다. 셋 중
    하나라도 맞으면 rate limit 이고, 셋 다 아니면 권한 문제(repo_unreachable)다.
    """
    if response.headers.get("x-ratelimit-remaining") == "0":
        return True
    if "retry-after" in response.headers:
        return True
    try:
        message = str(response.json().get("message", ""))
    except (ValueError, AttributeError):
        return False
    return "secondary rate limit" in message.lower()


def _retry_after_seconds(response: httpx.Response) -> int:
    """rate limit 재요청까지 기다릴 초를 계산한다.

    Retry-After를 우선하고, primary quota가 소진됐을 때만 reset을 사용한다.
    그 외에는 GitHub 지침에 따라 최소 60초 대기한다. Redis TTL은 항상 양수다.
    """
    retry_after = response.headers.get("retry-after")
    if retry_after is not None:
        try:
            return max(int(retry_after), 1)
        except ValueError:
            pass

    if response.headers.get("x-ratelimit-remaining") == "0":
        reset_at = response.headers.get("x-ratelimit-reset")
        if reset_at is not None:
            try:
                return max(int(reset_at) - int(time.time()), 1)
            except ValueError:
                pass
    # Secondary 제한은 primary reset 시각과 무관하다. 헤더가 불완전해도 대기를 남긴다.
    return 60


def _decode_readme(payload: Any) -> str | None:
    """README 응답의 base64 content 를 푼다. 입력: JSON. 출력: 본문 또는 None."""
    if not isinstance(payload, dict):
        return None
    content = payload.get("content")
    if not isinstance(content, str) or not content.strip():
        return None
    if payload.get("encoding") != "base64":
        return content
    try:
        return base64.b64decode(content).decode("utf-8", errors="replace")
    except (binascii.Error, ValueError):
        return None
