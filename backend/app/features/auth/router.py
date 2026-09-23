"""Browser navigation endpoints and idempotent session logout."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import JSONResponse, RedirectResponse, Response

from app.core.config import Settings
from app.core.deps import current_user, get_db
from app.core.errors import AppError, Reason
from app.core.security import clear_session_cookie, require_same_origin, set_session_cookie
from app.db.models.user import User
from app.features.auth.oauth import STATE_TTL_SECONDS, Purpose
from app.features.auth.service import finish_oauth

router = APIRouter(prefix="/auth", tags=["auth"])
Database = Annotated[AsyncSession, Depends(get_db)]


def _state_cookie(response: Response, settings: Settings, value: str | None) -> None:
    # 쿠키 경로는 브라우저 URL 기준이며 /api는 프록시가 백엔드로 전달할 때만 붙인다.
    if value is None:
        response.delete_cookie(
            "oauthState",
            path="/auth/github",
            httponly=True,
            secure=settings.cookie_secure,
            samesite="lax",
        )
    else:
        response.set_cookie(
            "oauthState",
            value,
            max_age=STATE_TTL_SECONDS,
            path="/auth/github",
            httponly=True,
            secure=settings.cookie_secure,
            samesite="lax",
        )


async def _start(request: Request, purpose: Purpose, user: User | None = None) -> Response:
    state, verifier = await request.app.state.oauth_states.create(
        purpose, user.id if user else None
    )
    response = RedirectResponse(
        request.app.state.oauth.authorize_url(state, verifier, purpose), status_code=302
    )
    response.headers["Cache-Control"] = "no-store"
    _state_cookie(response, request.app.state.settings, state)
    return response


@router.get("/github/login", include_in_schema=False)
async def login(request: Request) -> Response:
    return await _start(request, "login")


async def _browser_user(request: Request, db: AsyncSession) -> User | None:
    try:
        return await current_user(request, db)
    except AppError as error:
        if error.reason == Reason.UNAUTHENTICATED and error.status_code == 401:
            return None
        raise


@router.get("/github/link", include_in_schema=False)
async def link(request: Request, db: Database) -> Response:
    user = await _browser_user(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=302)
    return await _start(request, "link", user)


async def _callback(
    request: Request, db: AsyncSession, expected_purpose: Purpose | None = None
) -> Response:
    settings = request.app.state.settings
    try:
        record = await request.app.state.oauth_states.consume(
            request.query_params.get("state"), request.cookies.get("oauthState"), expected_purpose
        )
        purpose = record.purpose
        # 연동을 시작한 로그인 세션이 사라지거나 사용자가 바뀌면 계정을 연결하지 않는다.
        user = await _browser_user(request, db) if purpose == "link" else None
        if purpose == "link" and user is None:
            response: Response = RedirectResponse("/login", status_code=302)
        elif user is not None and user.id != record.user_id:
            raise AppError(Reason.INVALID_STATE)
        elif request.query_params.get("error") == "access_denied":
            response = RedirectResponse("/login?error=denied", status_code=302)
        else:
            code = request.query_params.get("code")
            if request.query_params.get("error") or not code or len(code) > 512:
                raise AppError(Reason.INVALID_CODE)
            user = await finish_oauth(
                db,
                request.app.state.oauth,
                request.app.state.cipher,
                request.app.state.redis,
                code,
                record.verifier,
                purpose,
                user.id if user else None,
            )
            response = RedirectResponse("/home", status_code=302)
            if purpose == "login":
                # 로그인 성공마다 세션 ID를 교체해 기존 ID를 계속 사용하는 세션 고정을 막는다.
                sessions = request.app.state.sessions
                sid = await sessions.create(user.id)
                try:
                    await sessions.delete(request.cookies.get(settings.session_cookie_name))
                except AppError:
                    await sessions.delete(sid)
                    raise
                set_session_cookie(response, settings, sid)
    except AppError as error:
        response = JSONResponse(error.to_envelope(), status_code=error.status_code)
    _state_cookie(response, settings, None)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@router.get("/github/callback", include_in_schema=False)
async def callback(request: Request, db: Database) -> Response:
    return await _callback(request, db)


@router.get("/github/link/callback", include_in_schema=False)
async def link_callback(request: Request, db: Database) -> Response:
    return await _callback(request, db, "link")


@router.post("/logout", status_code=204)
async def logout(request: Request) -> Response:
    require_same_origin(request)
    settings = request.app.state.settings
    await request.app.state.sessions.delete(request.cookies.get(settings.session_cookie_name))
    response = Response(status_code=204)
    clear_session_cookie(response, settings)
    return response
