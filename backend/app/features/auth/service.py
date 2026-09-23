"""GitHub identities are keyed by immutable provider ID, never mutable login."""

from uuid import UUID

from arq.connections import ArqRedis
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import TokenCipher
from app.core.errors import AppError, Reason
from app.core.security import require_active_user
from app.db.models.user import GithubAccount, User
from app.features.auth import queries
from app.features.auth.oauth import GitHubOAuth, GitHubProfile, OAuthToken, Purpose


async def upsert_github_user(
    db: AsyncSession,
    cipher: TokenCipher,
    profile: GitHubProfile,
    token: OAuthToken,
    user_id: UUID | None = None,
) -> User:
    encrypted = cipher.encrypt(token.access_token)
    if user_id is not None:
        identity = await queries.user_identity(db, user_id)
        if identity is None or identity[1].github_user_id != profile.github_user_id:
            raise AppError(Reason.GITHUB_ALREADY_LINKED)
    else:
        identity = await queries.github_identity(db, profile.github_user_id)
        if identity is None:
            user = User(name=profile.name, avatar_url=profile.avatar_url, status="active")
            account = GithubAccount(
                github_user_id=profile.github_user_id,
                login=profile.login,
                avatar_url=profile.avatar_url,
                public_repo_count=profile.public_repo_count,
                access_token_encrypted=encrypted,
                token_status="valid",
                token_scope=token.scope,
            )
            try:
                # 동시 최초 로그인은 GitHub ID의 유니크 제약으로 중복을 막는다.
                # 충돌한 삽입은 새 User까지 함께 되돌려 연결 없는 사용자가 남지 않게 한다.
                async with db.begin_nested():
                    await queries.add_identity(db, user, account)
                identity = (user, account)
            except IntegrityError:
                identity = await queries.github_identity(db, profile.github_user_id)
                if identity is None:
                    raise
    user, account = identity
    require_active_user(user.status)
    user.name, user.avatar_url = profile.name, profile.avatar_url
    account.login, account.avatar_url = profile.login, profile.avatar_url
    account.public_repo_count = profile.public_repo_count
    account.access_token_encrypted = encrypted
    account.token_status, account.token_scope = "valid", token.scope
    await db.commit()
    return user


async def finish_oauth(
    db: AsyncSession,
    oauth: GitHubOAuth,
    cipher: TokenCipher,
    redis: ArqRedis,
    code: str,
    verifier: str,
    purpose: Purpose,
    user_id: UUID | None = None,
) -> User:
    from app.features.analysis.pipeline.initial_sync import enqueue_initial_sync

    token = await oauth.exchange_code(code, verifier, purpose)
    profile = await oauth.fetch_profile(token.access_token)
    user = await upsert_github_user(db, cipher, profile, token, user_id)
    await enqueue_initial_sync(db, redis, user.id)
    return user
