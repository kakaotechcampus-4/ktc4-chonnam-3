"""GitHub public repository listing for initial synchronization."""

import httpx
from pydantic import ValidationError

from app.integrations.github.base import GithubApiError, RepoSummary


class GithubClient:
    def __init__(self, token: str, *, client: httpx.AsyncClient) -> None:
        self._token = token
        self._client = client

    async def list_repositories(self) -> list[RepoSummary]:
        url: str | None = "https://api.github.com/user/repos"
        params: dict[str, str | int] | None = {
            "visibility": "public",
            "affiliation": "owner",
            "per_page": 100,
            "sort": "pushed",
        }
        result: dict[int, RepoSummary] = {}
        visited: set[str] = set()
        while url is not None:
            target = httpx.URL(url)
            # 다음 페이지 링크에도 토큰을 보내므로 GitHub 목록 URL만 허용하고 순환을 차단한다.
            if (
                target.scheme != "https"
                or target.host != "api.github.com"
                or target.port not in (None, 443)
                or target.userinfo
                or target.path != "/user/repos"
                or url in visited
            ):
                raise GithubApiError("repo_unreachable")
            visited.add(url)
            try:
                response = await self._client.get(
                    target,
                    params=params,
                    headers={
                        "Accept": "application/vnd.github+json",
                        "Authorization": f"Bearer {self._token}",
                        "X-GitHub-Api-Version": "2022-11-28",
                    },
                    timeout=15,
                    follow_redirects=False,
                )
            except httpx.HTTPError as exc:
                raise GithubApiError("repo_unreachable") from exc
            if response.status_code == 401:
                raise GithubApiError("token_invalid", status_code=401)
            if response.status_code == 429 or (
                response.status_code == 403
                and (
                    response.headers.get("x-ratelimit-remaining") == "0"
                    or "retry-after" in response.headers
                )
            ):
                raise GithubApiError("rate_limited", status_code=response.status_code)
            if response.status_code != 200:
                raise GithubApiError("repo_unreachable", status_code=response.status_code)
            try:
                payload = response.json()
                if not isinstance(payload, list):
                    raise ValueError("Expected repository list")
                for item in payload:
                    repo = RepoSummary.model_validate(item)
                    if not repo.is_private:
                        result[repo.github_repo_id] = repo
            except (ValueError, ValidationError) as exc:
                raise GithubApiError("repo_unreachable") from exc
            url = response.links.get("next", {}).get("url")
            params = None
        return list(result.values())
