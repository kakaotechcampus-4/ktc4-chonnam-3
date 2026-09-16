"""DEVON JWT 갱신 세션과 독립적으로 서버에서 GitHub API를 호출한다."""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from cryptography.exceptions import InvalidTag
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.crypto import TokenCipher
from app.core.errors import AppError
from app.features.auth import queries, service
from app.features.auth.oauth import GitHubOAuth
from app.integrations.github.client import GitHubClient


class GitHubAPI:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        oauth: GitHubOAuth,
        cipher: TokenCipher,
        client: GitHubClient,
    ) -> None:
        self.sessions = sessions
        self.oauth = oauth
        self.cipher = cipher
        self.client = client

    async def get(
        self, user_id: UUID, path: str, params: dict[str, str] | None = None
    ) -> dict[str, Any] | list[Any]:
        # 다른 로그인·갱신이 거부된 토큰을 이미 교체한 경우에만 한 번 재시도한다.
        for _ in range(2):
            token = await self._access_token(user_id)
            try:
                return await self.client.get(path, token, params)
            except AppError as error:
                if error.reason != "token_invalid":
                    raise
                if await self._revoke_current(user_id, token):
                    raise
                # 교체 전 토큰의 늦은 401 응답으로 새 로그인까지 폐기해서는 안 된다.
        raise AppError("token_invalid")

    async def _access_token(self, user_id: UUID) -> str:
        token = None
        async with self.sessions.begin() as session:
            service.require_active(await queries.find_user(session, user_id))
            account = await queries.lock_github_account(session, user_id)
            if account is None or account.token_status != "valid":
                raise AppError("token_invalid")
            now = datetime.now(UTC)
            # 만료 시각이 NULL이면 기존 비만료형 토큰이다.
            # API 호출 중 만료에 대비해 60초 여유를 둔다.
            if account.token_expires_at is None or account.token_expires_at > now + timedelta(
                seconds=60
            ):
                return self._decrypt(account.access_token_encrypted)
            if (
                account.refresh_token_encrypted is None
                or account.refresh_token_expires_at is None
                or account.refresh_token_expires_at <= now
            ):
                # Refresh가 만료됐어도 Access의 유효기간이 남아 있으면 계속 사용할 수 있다.
                if account.token_expires_at > now:
                    return self._decrypt(account.access_token_encrypted)
                account.token_status = "revoked"
            else:
                try:
                    # 같은 계정 잠금으로 콜백의 토큰 저장과 다른 워커의 갱신도 직렬화한다.
                    # 다만 GitHub 토큰 교체와 DB 커밋을 하나의 원자적 작업으로 묶을 수는 없다.
                    pair = await self.oauth.refresh(self._decrypt(account.refresh_token_encrypted))
                except AppError as error:
                    if error.reason != "token_invalid":
                        raise
                    account.token_status = "revoked"
                else:
                    service.store_github_tokens(account, pair, self.cipher)
                    token = pair.access_token
        # 재연결이 필요하다는 오류를 전달하기 전에 폐기 상태를 커밋한다.
        if token is None:
            raise AppError("token_invalid")
        return token

    async def _revoke_current(self, user_id: UUID, rejected: str) -> bool:
        async with self.sessions.begin() as session:
            account = await queries.lock_github_account(session, user_id)
            if account is None or account.token_status != "valid":
                return True
            if self._decrypt(account.access_token_encrypted) != rejected:
                return False
            account.token_status = "revoked"
        return True

    def _decrypt(self, value: bytes) -> str:
        try:
            return self.cipher.decrypt(value)
        except (InvalidTag, ValueError, UnicodeError):
            # 암호화 키나 설정 오류만으로 GitHub가 토큰을 폐기했다고 판단할 수 없다.
            raise AppError("service_unavailable", 503) from None
