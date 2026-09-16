"""GitHub JSON GET 요청을 처리하며, 인증 정보와 DB 상태는 호출자가 관리한다."""

from typing import Any

import httpx

from app.core.errors import AppError


class GitHubClient:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client

    async def get(
        self, path: str, access_token: str, params: dict[str, str] | None = None
    ) -> dict[str, Any] | list[Any]:
        # 페이지네이션 URL이나 리다이렉트를 따라 다른 호스트로 인증 정보가 전달되지 않게 한다.
        if not path.startswith("/") or path.startswith("//") or any(c in path for c in "?#\\"):
            raise ValueError("Use a GitHub API path and separate query parameters")
        try:
            response = await self.client.get(
                "https://api.github.com" + path,
                params=params,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
                follow_redirects=False,
            )
            if response.status_code == 401:
                raise AppError("token_invalid")
            # 403·429는 권한 부족이나 요청 제한일 수 있으므로 토큰 폐기로 단정하지 않는다.
            if not response.is_success:
                raise AppError("provider_unavailable", 503)
            result = response.json()
            if not isinstance(result, (dict, list)):
                raise AppError("provider_unavailable", 503)
            return result
        except (httpx.HTTPError, ValueError):
            raise AppError("provider_unavailable", 503) from None
