"""One session authentication dependency for HTTP, SSE and WebSocket."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import HTTPConnection

from app.core.errors import AppError, Reason
from app.core.security import require_active_user, require_same_origin
from app.db.models.user import User
from app.db.session import get_db as get_db
from app.features.auth.session_store import SessionStore


async def current_user(
    connection: HTTPConnection, db: Annotated[AsyncSession, Depends(get_db)]
) -> User:
    require_same_origin(connection)
    sid = connection.cookies.get(connection.app.state.settings.session_cookie_name)
    sessions: SessionStore = connection.app.state.sessions
    user_id = await sessions.get(sid)
    if user_id is None or sid is None:
        raise AppError(Reason.UNAUTHENTICATED)
    user = await db.get(User, user_id)
    if user is None:
        raise AppError(Reason.UNAUTHENTICATED)
    require_active_user(user.status)
    # 사용자 조회 사이에 세션이 만료·삭제됐다면 쿠키를 연장하지 않고 인증을 거부한다.
    if not await sessions.touch(sid):
        raise AppError(Reason.UNAUTHENTICATED)
    connection.state.session_cookie_sid = sid
    return user
