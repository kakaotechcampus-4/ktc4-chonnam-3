"""Origin 검증이 세션 삭제·연장과 상태 변경보다 먼저 적용되는지 확인한다."""

import pytest
from fastapi import Depends

from app.core.deps import current_user
from app.db.models.user import User


@pytest.fixture
async def signed_in(client, app, db):
    user = User(name="Origin test", status="active")
    db.add(user)
    await db.commit()
    sid = await app.state.sessions.create(user.id)
    client.cookies.set("devon_session", sid)
    return sid


@pytest.mark.parametrize(
    "origin,referer",
    [
        (None, None),
        (None, "http://localhost:5173/home"),
        ("", None),
        ("null", None),
        ("https://untrusted.example", None),
        ("http://localhost:8000", None),
    ],
)
async def test_untrusted_logout_preserves_session_and_cookie(
    client, redis, signed_in, origin, referer
):
    key = f"auth:sess:{signed_in}"
    stored_user = await redis.get(key)
    await redis.expire(key, 30)
    request = client.build_request("POST", "/api/auth/logout")
    # headers={}만 넘기면 공통 클라이언트의 Origin이 남으므로 실제 헤더를 제거한다.
    request.headers.pop("origin", None)
    if origin is not None:
        request.headers["origin"] = origin
    if referer is not None:
        request.headers["referer"] = referer

    response = await client.send(request)

    assert response.status_code == 403
    assert response.json()["error"]["reason"] == "unauthenticated"
    assert "set-cookie" not in response.headers
    assert await redis.get(key) == stored_user
    assert 0 < await redis.ttl(key) <= 30
    assert (await client.get("/api/me")).status_code == 200


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
@pytest.mark.parametrize("origin", [None, "", "null", "https://untrusted.example"])
async def test_untrusted_write_never_runs_handler_or_extends_session(
    client, app, redis, signed_in, method, origin
):
    handled = []

    @app.api_route("/origin-test-write", methods=[method])
    async def write(user=Depends(current_user)):
        handled.append(user.id)
        return {"ok": True}

    key = f"auth:sess:{signed_in}"
    await redis.expire(key, 30)
    request = client.build_request(method, "/origin-test-write")
    request.headers.pop("origin", None)
    if origin is not None:
        request.headers["origin"] = origin

    response = await client.send(request)

    assert response.status_code == 403
    assert response.json()["error"]["reason"] == "unauthenticated"
    assert handled == []
    assert "set-cookie" not in response.headers
    assert 0 < await redis.ttl(key) <= 30


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
async def test_matching_origin_allows_write_and_extends_session(
    client, app, redis, signed_in, method
):
    @app.api_route("/origin-test-write", methods=[method])
    async def write(user=Depends(current_user)):
        return {"id": str(user.id)}

    key = f"auth:sess:{signed_in}"
    stored_user = (await redis.get(key)).decode()
    await redis.expire(key, 30)
    response = await client.request(method, "/origin-test-write")

    assert response.status_code == 200
    assert response.json() == {"id": stored_user}
    assert response.cookies["devon_session"] == signed_in
    assert await redis.ttl(key) > 1209500
