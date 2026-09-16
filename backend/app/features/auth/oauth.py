import base64
import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Literal
from urllib.parse import urlencode

import httpx
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import Settings
from app.core.errors import AppError


class GitHubProfile(BaseModel):
    model_config = ConfigDict(strict=True)
    id: int = Field(gt=0, le=9223372036854775807)
    login: str = Field(min_length=1, max_length=255)
    name: str | None = Field(default=None, max_length=255)
    avatar_url: str | None = Field(default=None, max_length=2048)


@dataclass(frozen=True)
class GitHubTokens:
    # A refresh rotates both secrets; neither may appear in identity or token repr output.
    access_token: str = field(repr=False)
    refresh_token: str = field(repr=False)
    scope: str
    expires_at: datetime
    refresh_expires_at: datetime


@dataclass(frozen=True)
class GitHubIdentity:
    profile: GitHubProfile
    tokens: GitHubTokens


class _GitHubTokenPayload(BaseModel):
    # Require a complete expiring pair, with integer lifetimes bounded before datetime arithmetic.
    model_config = ConfigDict(strict=True)
    access_token: str = Field(min_length=1, pattern=r"^\S+$", repr=False)
    refresh_token: str = Field(min_length=1, pattern=r"^\S+$", repr=False)
    token_type: Literal["bearer"]
    scope: str
    expires_in: int = Field(gt=0, le=2147483647)
    refresh_token_expires_in: int = Field(gt=0, le=2147483647)


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
        tokens = await self._request_tokens(
            {
                "redirect_uri": self.settings.github_redirect_uri,
                "code": code,
                "code_verifier": verifier,
            }
        )
        try:
            profile = await self.profile(tokens.access_token)
        except AppError:
            raise AppError("provider_unavailable", 503) from None
        return GitHubIdentity(profile, tokens)

    async def refresh(self, refresh_token: str) -> GitHubTokens:
        return await self._request_tokens(
            {"grant_type": "refresh_token", "refresh_token": refresh_token}
        )

    async def _request_tokens(self, data: dict[str, str]) -> GitHubTokens:
        client_secret = self.settings.github_client_secret.get_secret_value()
        if not self.settings.github_client_id or not client_secret:
            raise AppError("provider_unavailable", 503)
        try:
            # Anchor expiry before network I/O so response latency never extends a token's lifetime.
            requested_at = datetime.now(UTC)
            response = await self.client.post(
                "https://github.com/login/oauth/access_token",
                headers={"Accept": "application/json"},
                follow_redirects=False,
                data={
                    "client_id": self.settings.github_client_id,
                    "client_secret": client_secret,
                    **data,
                },
            )
            # Rate limits, redirects, and server failures cannot prove credentials were revoked.
            if response.status_code not in {200, 400, 401}:
                raise AppError("provider_unavailable", 503)
            payload = response.json()
            if not isinstance(payload, dict):
                raise AppError("provider_unavailable", 503)
            refreshing = data.get("grant_type") == "refresh_token"
            if refreshing and payload.get("error") == "bad_refresh_token":
                raise AppError("token_invalid", 401)
            if not refreshing and payload.get("error") == "bad_verification_code":
                raise AppError("invalid_code", 400)
            if not response.is_success or "error" in payload:
                raise AppError("provider_unavailable", 503)
            validated = _GitHubTokenPayload.model_validate(payload)
            if "read:user" not in validated.scope.replace(",", " ").split():
                raise AppError("provider_unavailable", 503)
            return GitHubTokens(
                access_token=validated.access_token,
                refresh_token=validated.refresh_token,
                scope=validated.scope,
                expires_at=requested_at + timedelta(seconds=validated.expires_in),
                refresh_expires_at=requested_at
                + timedelta(seconds=validated.refresh_token_expires_in),
            )
        except (httpx.HTTPError, ValueError, OverflowError):
            raise AppError("provider_unavailable", 503) from None

    async def profile(self, access_token: str) -> GitHubProfile:
        try:
            response = await self.client.get(
                "https://api.github.com/user",
                follow_redirects=False,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
            if response.status_code == 401:
                raise AppError("token_invalid", 401)
            if not response.is_success:
                raise AppError("provider_unavailable", 503)
            return GitHubProfile.model_validate(response.json())
        except (httpx.HTTPError, ValueError):
            raise AppError("provider_unavailable", 503) from None
