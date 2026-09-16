"""GitHub JSON GET requests; credentials and database state belong to the caller."""

from typing import Any

import httpx

from app.core.errors import AppError


class GitHubClient:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client

    async def get(
        self, path: str, access_token: str, params: dict[str, str] | None = None
    ) -> dict[str, Any] | list[Any]:
        # Credentials must never follow a pagination URL or redirect to another host.
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
            # A 403/429 may be a scope or rate-limit issue, not proof of token revocation.
            if not response.is_success:
                raise AppError("provider_unavailable", 503)
            result = response.json()
            if not isinstance(result, (dict, list)):
                raise AppError("provider_unavailable", 503)
            return result
        except (httpx.HTTPError, ValueError):
            raise AppError("provider_unavailable", 503) from None
