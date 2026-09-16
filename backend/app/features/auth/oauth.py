import base64
import hashlib
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.config import Settings
from app.core.errors import AppError


class GitHubProfile(BaseModel):
    model_config = ConfigDict(strict=True)
    id: int = Field(gt=0, le=9223372036854775807)
    login: str = Field(min_length=1, max_length=255)
    name: str | None = Field(default=None, max_length=255)
    avatar_url: str | None = Field(default=None, max_length=2048)


@dataclass
class GitHubIdentity:
    profile: GitHubProfile
    access_token: str
    scope: str


class GitHubOAuth:
    def __init__(self, settings: Settings, client: httpx.AsyncClient) -> None:
        self.settings = settings
        self.client = client

    def authorization_url(self, state: str, verifier: str) -> str:
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .rstrip(b"=")
            .decode()
        )
        return "https://github.com/login/oauth/authorize?" + urlencode(
            {
                "client_id": self.settings.github_client_id,
                "redirect_uri": self.settings.github_redirect_uri,
                "scope": "read:user",
                "state": state,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }
        )

    async def exchange(self, code: str, verifier: str) -> GitHubIdentity:
        if not code or len(code) > 2048:
            raise AppError("invalid_code", 400)
        try:
            response = await self.client.post(
                "https://github.com/login/oauth/access_token",
                headers={"Accept": "application/json"},
                data={
                    "client_id": self.settings.github_client_id,
                    "client_secret": self.settings.github_client_secret.get_secret_value(),
                    "redirect_uri": self.settings.github_redirect_uri,
                    "code": code,
                    "code_verifier": verifier,
                },
            )
            if response.status_code >= 500 or response.status_code == 429:
                raise AppError("provider_unavailable", 503)
            payload = response.json()
            if not isinstance(payload, dict):
                raise AppError("provider_unavailable", 503)
            if payload.get("error") == "bad_verification_code":
                raise AppError("invalid_code", 400)
            # Storage supports only non-expiring OAuth App tokens, with no refresh flow.
            if {"expires_in", "refresh_token", "refresh_token_expires_in"} & payload.keys():
                raise AppError("provider_unavailable", 503)
            token = payload.get("access_token")
            scope = payload.get("scope")
            if (
                response.is_error
                or not isinstance(token, str)
                or not token
                or not isinstance(scope, str)
                or "read:user" not in scope.replace(",", " ").split()
            ):
                raise AppError("provider_unavailable", 503)
            response = await self.client.get(
                "https://api.github.com/user",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
            if response.is_error:
                raise AppError("provider_unavailable", 503)
            return GitHubIdentity(GitHubProfile.model_validate(response.json()), token, scope)
        except (httpx.HTTPError, ValueError, ValidationError):
            raise AppError("provider_unavailable", 503) from None
