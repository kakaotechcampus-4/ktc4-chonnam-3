from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import TokenCipher
from app.core.errors import AppError
from app.core.security import Tokens
from app.db.models.user import AuthSession, GitHubAccount, User
from app.features.auth import queries
from app.features.auth.oauth import GitHubIdentity, GitHubTokens


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
    # Refresh 폐기 후에도 Access는 만료까지 유효하지만, 계정 상태는 계속 확인한다.
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
            )
            session.add(account)
        else:
            user = require_active(await queries.find_user(session, account.user_id))
            user.display_name = identity.profile.name or identity.profile.login
            user.avatar_url = identity.profile.avatar_url
            user.last_login_at = datetime.now(UTC)
            account.login = identity.profile.login
        store_github_tokens(account, identity.tokens, cipher)
    return user


def store_github_tokens(account: GitHubAccount, pair: GitHubTokens, cipher: TokenCipher) -> None:
    # GitHub는 두 토큰을 함께 교체하므로 호출자의 트랜잭션에서 토큰 쌍을 함께 저장한다.
    account.access_token_encrypted = cipher.encrypt(pair.access_token)
    account.refresh_token_encrypted = cipher.encrypt(pair.refresh_token)
    account.token_expires_at = pair.expires_at
    account.refresh_token_expires_at = pair.refresh_expires_at
    account.token_status = "valid"
    account.token_scope = pair.scope


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
        # 이미 폐기된 세대의 토큰으로는 이전 재사용 감지 후 생성된 세션을 폐기할 수 없다.
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
            # 유효한 세션에서 재사용이 감지되면 이 사용자의 같은 세대 Refresh를 모두 폐기한다.
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
    # 재사용으로 인한 폐기를 먼저 커밋한 뒤 예외를 전달해야 변경이 롤백되지 않는다.
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
            # 동시 갱신으로 jti가 바뀔 수 있으므로 jti가 아닌 로그인 세션을 기준으로 삭제한다.
            await queries.delete_auth_session(
                session, UUID(claims["sid"]), user.id, UUID(claims["generation"])
            )


async def cleanup_expired_sessions(session: AsyncSession) -> int:
    async with session.begin():
        return await queries.delete_expired_sessions(session, datetime.now(UTC))
