"""Server-side GitHub API access, independent of DEVON JWT refresh sessions."""

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
        # Retry once only when another login/refresh replaced the rejected token.
        for _ in range(2):
            token = await self._access_token(user_id)
            try:
                return await self.client.get(path, token, params)
            except AppError as error:
                if error.reason != "token_invalid":
                    raise
                if await self._revoke_current(user_id, token):
                    raise
                # A delayed 401 for a replaced token must not revoke the new login.
        raise AppError("token_invalid")

    async def _access_token(self, user_id: UUID) -> str:
        token = None
        async with self.sessions.begin() as session:
            service.require_active(await queries.find_user(session, user_id))
            account = await queries.lock_github_account(session, user_id)
            if account is None or account.token_status != "valid":
                raise AppError("token_invalid")
            now = datetime.now(UTC)
            # NULL expiry is a preserved legacy token; the margin covers in-flight API calls.
            if account.token_expires_at is None or account.token_expires_at > now + timedelta(
                seconds=60
            ):
                return self._decrypt(account.access_token_encrypted)
            if (
                account.refresh_token_encrypted is None
                or account.refresh_token_expires_at is None
                or account.refresh_token_expires_at <= now
            ):
                # Refresh expiry alone does not invalidate an access token still in its lifetime.
                if account.token_expires_at > now:
                    return self._decrypt(account.access_token_encrypted)
                account.token_status = "revoked"
            else:
                try:
                    # The account lock also covers callback updates and other workers.
                    # A remote rotation and our DB commit cannot be one atomic operation.
                    pair = await self.oauth.refresh(self._decrypt(account.refresh_token_encrypted))
                except AppError as error:
                    if error.reason != "token_invalid":
                        raise
                    account.token_status = "revoked"
                else:
                    service.store_github_tokens(account, pair, self.cipher)
                    token = pair.access_token
        # Commit invalidation before reporting reconnect-required to the caller.
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
            # Key/configuration failures do not prove that GitHub revoked a token.
            raise AppError("service_unavailable", 503) from None
