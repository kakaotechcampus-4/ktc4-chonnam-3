"""FastAPI 의존성 - get_db / current_user / require_github_token.

docs/layer-rules.md 1절 / task-06
"""

from collections.abc import AsyncIterator
from typing import Annotated

from arq.connections import ArqRedis
from fastapi import Cookie, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AppError, ErrorReason
from app.db.models.user import GithubAccount, User
from app.db.session import get_sessionmaker
from app.features.auth import session_store
from app.shared.enums import TokenStatus


async def get_db() -> AsyncIterator[AsyncSession]:
    """요청 단위 세션. commit 은 service 가 한다."""
    async with get_sessionmaker()() as session:
        yield session


async def get_arq(request: Request) -> ArqRedis:
    """lifespan 에서 만든 ARQ pool. enqueue 는 service 에서만 호출한다."""
    pool = getattr(request.app.state, "arq", None)
    if pool is None:  # pragma: no cover - 기동 실패 시에만
        raise AppError(ErrorReason.INTERNAL_ERROR, message="queue is not available")
    return pool  # type: ignore[no-any-return]


async def current_user(
    db: Annotated[AsyncSession, Depends(get_db)],
    session_id: Annotated[str | None, Cookie(alias=get_settings().session_cookie_name)] = None,
) -> User:
    """세션 쿠키 -> users 행. JWT 전달 방식 확정(PENDING_FE) 시 이 함수만 바꾼다."""
    if not session_id:
        raise AppError(ErrorReason.UNAUTHENTICATED)
    user_id = await session_store.resolve_session(session_id)
    if user_id is None:
        raise AppError(ErrorReason.UNAUTHENTICATED)
    user = await db.get(User, user_id)
    if user is None:
        raise AppError(ErrorReason.UNAUTHENTICATED)
    if user.status == "suspended":
        raise AppError(ErrorReason.ACCOUNT_SUSPENDED)
    if user.status == "withdrawn":
        raise AppError(ErrorReason.ACCOUNT_WITHDRAWN)
    return user


async def require_github_token(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(current_user)],
) -> GithubAccount:
    """GitHub 대행 호출 전에 token_status 를 먼저 본다 (revoked 면 호출하지 않는다)."""
    account = (
        await db.execute(select(GithubAccount).where(GithubAccount.user_id == user.id))
    ).scalar_one_or_none()
    if account is None or account.token_status != TokenStatus.VALID:
        raise AppError(ErrorReason.TOKEN_INVALID)
    return account


CurrentUser = Annotated[User, Depends(current_user)]
DbSession = Annotated[AsyncSession, Depends(get_db)]
ArqPool = Annotated[ArqRedis, Depends(get_arq)]
