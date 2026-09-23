"""Cookie policy shared by REST, streaming responses and WebSocket handshakes."""

from starlette.requests import HTTPConnection
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import Settings
from app.core.errors import AppError, Reason


def require_active_user(status: str) -> None:
    if status == "suspended":
        raise AppError(Reason.ACCOUNT_SUSPENDED)
    if status == "withdrawn":
        raise AppError(Reason.ACCOUNT_WITHDRAWN)
    if status != "active":
        raise AppError(Reason.UNAUTHENTICATED)


def require_same_origin(connection: HTTPConnection) -> None:
    if connection.scope["type"] == "http" and connection.scope["method"] in {
        "GET",
        "HEAD",
        "OPTIONS",
    }:
        return
    origin = connection.headers.get("origin")
    expected = connection.app.state.settings.frontend_origin.rstrip("/")
    if (origin is not None and origin != expected) or (
        connection.scope["type"] == "websocket" and origin is None
    ):
        raise AppError(Reason.UNAUTHENTICATED, status_code=403)


def set_session_cookie(response: Response, settings: Settings, sid: str) -> None:
    response.set_cookie(
        settings.session_cookie_name,
        sid,
        max_age=settings.session_ttl_seconds,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path="/",
    )


def clear_session_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        settings.session_cookie_name,
        path="/",
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
    )


class SessionCookieMiddleware:
    """Append the sliding cookie to the actual response, including streams and WS."""

    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        self.app = app
        self.settings = settings

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return

        async def send_with_cookie(message: Message) -> None:
            sid = scope.get("state", {}).get("session_cookie_sid")
            # SSE 응답과 WS 수락에도 Redis TTL과 같은 쿠키 만료 연장을 적용한다.
            if sid and message["type"] in {"http.response.start", "websocket.accept"}:
                headers = list(message.get("headers", []))
                if message["type"] == "http.response.start":
                    headers = [
                        (name, value) for name, value in headers if name.lower() != b"cache-control"
                    ]
                    headers.append((b"cache-control", b"private, no-store"))
                prefix = (self.settings.session_cookie_name + "=").encode()
                # 라우터가 발급·삭제한 쿠키가 있으면 자동 연장 쿠키로 덮어쓰지 않는다.
                if not any(
                    name.lower() == b"set-cookie" and value.startswith(prefix)
                    for name, value in headers
                ):
                    cookie = Response()
                    set_session_cookie(cookie, self.settings, sid)
                    headers.extend(
                        (name, value) for name, value in cookie.raw_headers if name == b"set-cookie"
                    )
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_cookie)
