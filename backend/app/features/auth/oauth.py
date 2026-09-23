"""GitHub OAuth boundary and single-use browser-bound state with PKCE."""

import base64
import hashlib
import json
import re
import secrets
from dataclasses import dataclass, field
from typing import Literal
from urllib.parse import urlencode
from uuid import UUID

import httpx
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import Settings
from app.core.errors import AppError, Reason
from app.core.logging import get_logger

Purpose = Literal["login", "link"]
_STATE = re.compile(r"[A-Za-z0-9_-]{43}")
STATE_TTL_SECONDS = 600


@dataclass(frozen=True)
class OAuthState:
    purpose: Purpose
    verifier: str = field(repr=False)
    user_id: UUID | None = None


class OAuthStateStore:
    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    async def create(self, purpose: Purpose, user_id: UUID | None = None) -> tuple[str, str]:
        verifier = secrets.token_urlsafe(32)
        payload = json.dumps(
            {
                "purpose": purpose,
                "verifier": verifier,
                "user_id": str(user_id) if user_id else None,
            }
        )
        try:
            while True:
                state = secrets.token_urlsafe(32)
                if await self.redis.set(
                    f"auth:oauth:{state}", payload, ex=STATE_TTL_SECONDS, nx=True
                ):
                    return state, verifier
        except RedisError:
            raise AppError(Reason.INTERNAL_ERROR) from None

    async def consume(
        self, state: str | None, cookie: str | None, purpose: Purpose | None = None
    ) -> OAuthState:
        # 로그인을 시작한 브라우저인지 먼저 확인해 다른 브라우저가 state를 소모하지 못하게 한다.
        if (
            state is None
            or cookie is None
            or not _STATE.fullmatch(state)
            or not _STATE.fullmatch(cookie)
            or not secrets.compare_digest(state, cookie)
        ):
            raise AppError(Reason.INVALID_STATE)
        try:
            # 조회와 삭제를 원자적으로 수행해 같은 callback의 동시 요청·재사용을 막는다.
            raw = await self.redis.getdel(f"auth:oauth:{state}")
        except RedisError:
            raise AppError(Reason.INTERNAL_ERROR) from None
        if raw is None:
            raise AppError(Reason.INVALID_STATE)
        try:
            data = json.loads(raw)
            stored_purpose = data["purpose"]
            if (
                stored_purpose not in {"login", "link"}
                or (purpose is not None and stored_purpose != purpose)
                or not _STATE.fullmatch(data["verifier"])
            ):
                raise ValueError
            user_id = UUID(data["user_id"]) if data["user_id"] else None
            if (stored_purpose == "link") != (user_id is not None):
                raise ValueError
            return OAuthState(stored_purpose, data["verifier"], user_id)
        except (ValueError, TypeError, KeyError):
            raise AppError(Reason.INVALID_STATE) from None


@dataclass(frozen=True)
class OAuthToken:
    access_token: str = field(repr=False)
    scope: str


@dataclass(frozen=True)
class GitHubProfile:
    github_user_id: int
    login: str
    name: str
    avatar_url: str | None
    public_repo_count: int


class GitHubOAuth:
    def __init__(self, settings: Settings, client: httpx.AsyncClient) -> None:
        self.settings = settings
        self.client = client

    def authorize_url(self, state: str, verifier: str, purpose: Purpose) -> str:
        # verifier는 서버에만 보관하고 해시만 보내 탈취된 code의 단독 교환을 막는다.
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .rstrip(b"=")
            .decode()
        )
        return "https://github.com/login/oauth/authorize?" + urlencode(
            {
                "client_id": self.settings.github_client_id,
                "redirect_uri": self.settings.github_redirect_uri,
                "scope": self.settings.github_login_scope
                if purpose == "login"
                else self.settings.github_link_scope,
                "state": state,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }
        )

    async def exchange_code(self, code: str, verifier: str, purpose: Purpose) -> OAuthToken:
        try:
            response = await self.client.post(
                "https://github.com/login/oauth/access_token",
                headers={"Accept": "application/json"},
                data={
                    "client_id": self.settings.github_client_id,
                    "client_secret": self.settings.github_client_secret.get_secret_value(),
                    "code": code,
                    "redirect_uri": self.settings.github_redirect_uri,
                    "code_verifier": verifier,
                },
                timeout=15.0,
                follow_redirects=False,
            )
        except httpx.HTTPError:
            raise AppError(Reason.PROVIDER_UNAVAILABLE) from None
        if response.status_code in (400, 401):
            raise AppError(Reason.INVALID_CODE)
        if response.status_code != 200:
            raise AppError(Reason.PROVIDER_UNAVAILABLE)
        data = self._json_object(response)
        if data.get("error") == "bad_verification_code":
            raise AppError(Reason.INVALID_CODE)
        token = data.get("access_token")
        scope = data.get("scope")
        if (
            data.get("error")
            or not isinstance(token, str)
            or not token
            or not token.isascii()
            or not token.isprintable()
            or any(char.isspace() for char in token)
            or data.get("token_type") != "bearer"
            or not isinstance(scope, str)
        ):
            raise AppError(Reason.PROVIDER_UNAVAILABLE)
        # Sprint 1은 장기 토큰만 저장하므로 갱신이 필요한 응답을 로그인 성공으로 처리하지 않는다.
        if any(key in data for key in ("refresh_token", "expires_in", "refresh_token_expires_in")):
            get_logger(__name__).warning("github_oauth_token_mode_unsupported")
            raise AppError(
                Reason.PROVIDER_UNAVAILABLE,
                message="GitHub 로그인 설정이 서비스와 맞지 않습니다. 관리자에게 문의해주세요.",
            )
        return OAuthToken(token, scope)

    async def fetch_profile(self, token: str) -> GitHubProfile:
        try:
            response = await self.client.get(
                "https://api.github.com/user",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                },
                timeout=15.0,
                follow_redirects=False,
            )
        except httpx.HTTPError:
            raise AppError(Reason.PROVIDER_UNAVAILABLE) from None
        if response.status_code == 401:
            raise AppError(Reason.INVALID_CODE)
        if response.status_code != 200:
            raise AppError(Reason.PROVIDER_UNAVAILABLE)
        data = self._json_object(response)
        github_id, login = data.get("id"), data.get("login")
        name, avatar = data.get("name"), data.get("avatar_url")
        count = data.get("public_repos")
        if (
            type(github_id) is not int
            or github_id <= 0
            or github_id > 9223372036854775807
            or not isinstance(login, str)
            or not login.strip()
            or (name is not None and not isinstance(name, str))
            or (avatar is not None and not isinstance(avatar, str))
            or type(count) is not int
            or count < 0
        ):
            raise AppError(Reason.PROVIDER_UNAVAILABLE)
        return GitHubProfile(github_id, login, name or login, avatar, count)

    @staticmethod
    def _json_object(response: httpx.Response) -> dict[str, object]:
        try:
            data = response.json()
        except ValueError:
            raise AppError(Reason.PROVIDER_UNAVAILABLE) from None
        if not isinstance(data, dict):
            raise AppError(Reason.PROVIDER_UNAVAILABLE)
        return data
