from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import TokenCipher
from app.core.errors import AppError
from app.core.security import Tokens
from app.db.models.user import AuthSession, GitHubAccount, User
from app.features.auth import queries
from app.features.auth.oauth import GitHubIdentity


def require_active(user: User | None) -> User:
    if user is None:
        raise AppError("unauthenticated")
    if user.status != "active":
        raise AppError(f"account_{user.status}", 403)
    return user


async def authenticate(session: AsyncSession, tokens: Tokens, token: str | None) -> User:
    if not token:
        raise AppError("unauthenticated")
    claims = tokens.decode(token, "access")
    # Refresh revocation does not invalidate access; account status still applies.
    return require_active(await queries.find_user(session, UUID(claims["sub"])))


async def save_identity(
    session: AsyncSession, identity: GitHubIdentity, cipher: TokenCipher
) -> User:
    async with session.begin():
        await queries.lock_github_identity(session, identity.profile.id)
        account = await queries.find_github_account(session, identity.profile.id)
        if account is None:
            user = User(
                display_name=identity.profile.name or identity.profile.login,
                avatar_url=identity.profile.avatar_url,
                status="active",
                last_login_at=datetime.now(UTC),
            )
            session.add(user)
            await session.flush()
            account = GitHubAccount(
                user_id=user.id,
                github_user_id=identity.profile.id,
                login=identity.profile.login,
                access_token_encrypted=cipher.encrypt(identity.access_token),
                token_status="valid",
                token_scope=identity.scope,
            )
            session.add(account)
        else:
            user = require_active(await queries.find_user(session, account.user_id))
            user.display_name = identity.profile.name or identity.profile.login
            user.avatar_url = identity.profile.avatar_url
            user.last_login_at = datetime.now(UTC)
            account.login = identity.profile.login
            account.access_token_encrypted = cipher.encrypt(identity.access_token)
            account.token_status = "valid"
            account.token_scope = identity.scope
    return user


async def issue_tokens(session: AsyncSession, tokens: Tokens, user_id: str) -> tuple[str, str]:
    async with session.begin():
        user = require_active(await queries.lock_user(session, UUID(user_id)))
        record = AuthSession(
            id=uuid4(),
            user_id=user.id,
            generation=user.refresh_generation,
            refresh_jti=uuid4(),
        )
        session.add(record)
        pair = (
            tokens.access(user_id),
            tokens.encode(
                user_id,
                "refresh",
                sid=str(record.id),
                generation=str(record.generation),
                jti=str(record.refresh_jti),
            ),
        )
        record.expires_at = datetime.fromtimestamp(tokens.decode(pair[1], "refresh")["exp"], UTC)
    return pair


async def refresh(session: AsyncSession, tokens: Tokens, token: str | None) -> tuple[str, str]:
    if not token:
        raise AppError("refresh_token_invalid")
    claims = tokens.decode(token, "refresh")
    pair = None
    async with session.begin():
        user = require_active(await queries.lock_user(session, UUID(claims["sub"])))
        # Stale generations must not revoke sessions created after an earlier replay.
        if user.refresh_generation != UUID(claims["generation"]):
            raise AppError("refresh_token_invalid")
        record = await queries.find_auth_session(session, UUID(claims["sid"]))
        if (
            record is None
            or record.user_id != user.id
            or record.generation != user.refresh_generation
            or record.expires_at <= datetime.now(UTC)
        ):
            raise AppError("refresh_token_invalid")
        if record.refresh_jti != UUID(claims["jti"]):
            # Replay in a live session invalidates every refresh in this generation.
            user.refresh_generation = uuid4()
        else:
            record.refresh_jti = uuid4()
            pair = (
                tokens.access(claims["sub"]),
                tokens.encode(
                    claims["sub"],
                    "refresh",
                    sid=claims["sid"],
                    generation=claims["generation"],
                    jti=str(record.refresh_jti),
                ),
            )
            record.expires_at = datetime.fromtimestamp(
                tokens.decode(pair[1], "refresh")["exp"], UTC
            )
    # Replay revocation must commit before the failure reaches the request boundary.
    if pair is None:
        raise AppError("refresh_token_invalid")
    return pair


async def logout(session: AsyncSession, tokens: Tokens, token: str | None) -> None:
    if not token:
        return
    try:
        claims = tokens.decode(token, "refresh")
    except AppError:
        return
    async with session.begin():
        user = await queries.lock_user(session, UUID(claims["sub"]))
        if user is not None:
            # Match the login, not jti: a concurrent refresh may have rotated it.
            await queries.delete_auth_session(
                session, UUID(claims["sid"]), user.id, UUID(claims["generation"])
            )


async def cleanup_expired_sessions(session: AsyncSession) -> int:
    async with session.begin():
        return await queries.delete_expired_sessions(session, datetime.now(UTC))
