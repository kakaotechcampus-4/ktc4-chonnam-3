"""부하 스모크 스크립트의 계산과 판정을 서버 없이 검사한다 (httpx.MockTransport)."""

import httpx

from scripts.load_smoke import COOKIE_NAME, Result, evaluate, percentile, run


def test_percentile_uses_nearest_rank():
    values = [float(n) for n in range(1, 101)]

    assert percentile(values, 50) == 50.0
    assert percentile(values, 95) == 95.0
    assert percentile([7.0], 95) == 7.0
    assert percentile([], 95) == 0.0


async def test_run_counts_errors_per_path_and_sends_session_cookie():
    seen_cookies: dict[str, str | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen_cookies[request.url.path] = request.headers.get("cookie")
        return httpx.Response(500 if request.url.path == "/api/me/home" else 200)

    results = await run(
        "http://test",
        requests=10,
        concurrency=4,
        session="abc",
        transport=httpx.MockTransport(handler),
    )

    by_path = {r.path: r for r in results}
    assert set(by_path) == {"/api/health", "/api/me", "/api/me/home"}
    assert by_path["/api/health"].errors == 0
    assert by_path["/api/me/home"].errors == 10
    assert all(r.requests == 10 for r in results)
    assert seen_cookies["/api/me"] == f"{COOKIE_NAME}=abc"


async def test_run_skips_authed_paths_without_session():
    results = await run(
        "http://test",
        requests=3,
        concurrency=2,
        session=None,
        transport=httpx.MockTransport(lambda request: httpx.Response(200)),
    )

    assert [r.path for r in results] == ["/api/health"]


async def test_run_counts_connection_failures_as_errors():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    (result,) = await run(
        "http://test",
        requests=5,
        concurrency=2,
        session=None,
        transport=httpx.MockTransport(handler),
    )

    assert result.errors == 5


def test_evaluate_flags_error_rate_and_slow_p95():
    ok = Result("/api/health", 100, 0, 5.0, 20.0)
    bad = Result("/api/me", 100, 2, 50.0, 900.0)

    assert evaluate([ok], max_p95_ms=500, max_error_rate=0.0) == []
    failures = evaluate([ok, bad], max_p95_ms=500, max_error_rate=0.0)
    assert len(failures) == 2
    assert all("/api/me" in f for f in failures)
