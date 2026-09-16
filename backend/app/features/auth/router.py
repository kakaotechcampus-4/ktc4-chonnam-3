from fastapi import APIRouter, Request
from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError
from starlette.responses import RedirectResponse, Response

from app.core.deps import DbSession
from app.core.errors import AppError
from app.core.security import ACCESS_TTL, REFRESH_TTL
from app.features.auth import service

router = APIRouter(prefix="/auth")


def set_cookie(
    response: Response, request: Request, name: str, value: str, path: str, ttl: int
) -> None:
    response.set_cookie(
        name,
        value,
        max_age=ttl,
        path=path,
        secure=request.app.state.settings.cookie_secure,
        httponly=True,
        samesite="lax",
    )


def clear_cookie(response: Response, request: Request, name: str, path: str) -> None:
    response.delete_cookie(
        name,
        path=path,
        secure=request.app.state.settings.cookie_secure,
        httponly=True,
        samesite="lax",
    )


def set_tokens(response: Response, request: Request, pair: tuple[str, str]) -> None:
    set_cookie(response, request, "accessToken", pair[0], "/", ACCESS_TTL)
    set_cookie(response, request, "refreshToken", pair[1], "/api/auth", REFRESH_TTL)


def require_origin(request: Request) -> None:
    if request.headers.get("origin") != request.app.state.settings.frontend_origin:
        raise AppError("invalid_origin", 403)


@router.get("/github/login")
async def login(request: Request) -> Response:
    if not request.app.state.settings.github_client_id:
        raise AppError("service_unavailable", 503)
    state, binding, verifier = await request.app.state.oauth_states.start_state()
    response = RedirectResponse(
        request.app.state.oauth.authorization_url(state, verifier), status_code=302
    )
    set_cookie(response, request, "oauthState", binding, "/api/auth/github", 600)
    return response


@router.get("/github/callback")
async def callback(request: Request, session: DbSession) -> Response:
    settings = request.app.state.settings
    try:
        verifier = await request.app.state.oauth_states.consume_state(
            request.query_params.get("state"), request.cookies.get("oauthState")
        )
        if request.query_params.get("error"):
            raise AppError(
                "denied" if request.query_params["error"] == "access_denied" else "invalid_code",
                400,
            )
        identity = await request.app.state.oauth.exchange(
            request.query_params.get("code", ""), verifier
        )
        user = await service.save_identity(session, identity, request.app.state.cipher)
        pair = await service.issue_tokens(session, request.app.state.tokens, str(user.id))
        response = RedirectResponse(settings.frontend_origin + "/home", status_code=302)
        set_tokens(response, request, pair)
    except (RedisError, SQLAlchemyError):
        response = RedirectResponse(
            settings.frontend_origin + "/login?error=service_unavailable", status_code=302
        )
    except AppError as error:
        response = RedirectResponse(
            settings.frontend_origin + "/login?error=" + error.reason, status_code=302
        )
    except Exception:
        response = RedirectResponse(
            settings.frontend_origin + "/login?error=internal_error", status_code=302
        )
    clear_cookie(response, request, "oauthState", "/api/auth/github")
    return response


@router.post("/refresh", status_code=204)
async def refresh(request: Request, session: DbSession) -> Response:
    require_origin(request)
    pair = await service.refresh(
        session,
        request.app.state.tokens,
        request.cookies.get("refreshToken"),
    )
    response = Response(status_code=204)
    set_tokens(response, request, pair)
    return response


@router.post("/logout", status_code=204)
async def logout(request: Request, session: DbSession) -> Response:
    require_origin(request)
    # DB 장애로 폐기에 실패하면 재시도할 수 있도록 쿠키를 유지한다.
    await service.logout(session, request.app.state.tokens, request.cookies.get("refreshToken"))
    response = Response(status_code=204)
    clear_cookie(response, request, "accessToken", "/")
    clear_cookie(response, request, "refreshToken", "/api/auth")
    return response
