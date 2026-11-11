"""로컬 서버 부하 스모크 — httpx + asyncio, 새 의존성 없음.

사용 (백엔드를 먼저 띄운 뒤):
    uv run python -m scripts.load_smoke --base-url http://127.0.0.1:8000
인증 경로(/api/me, /api/me/home)는 DEVON_SESSION=<devon_session 쿠키 값>이 있을 때만 함께 잰다.
운영·배포 서버에는 실행하지 않는다. LLM·외부 호출 경로와 WebSocket은 범위 밖이다.

# ponytail: 단일 프로세스 스모크다. 정밀한 부하·장시간 측정은 k6/Locust로 교체한다.
"""

from __future__ import annotations

import argparse
import asyncio
import math
import os
import sys
import time
from dataclasses import dataclass

import httpx

COOKIE_NAME = "devon_session"
PUBLIC_PATHS = ("/api/health",)
AUTHED_PATHS = ("/api/me", "/api/me/home")


@dataclass(frozen=True)
class Result:
    path: str
    requests: int
    errors: int
    p50_ms: float
    p95_ms: float

    @property
    def error_rate(self) -> float:
        return self.errors / self.requests if self.requests else 0.0


def percentile(sorted_ms: list[float], p: float) -> float:
    """nearest-rank 백분위. 보간하지 않아 실제로 관측된 값만 돌려준다."""
    if not sorted_ms:
        return 0.0
    rank = max(1, math.ceil(p / 100 * len(sorted_ms)))
    return sorted_ms[rank - 1]


async def run_path(client: httpx.AsyncClient, path: str, requests: int, concurrency: int) -> Result:
    gate = asyncio.Semaphore(concurrency)
    latencies: list[float] = []
    errors = 0

    async def one() -> None:
        nonlocal errors
        async with gate:
            start = time.perf_counter()
            try:
                ok = (await client.get(path)).status_code == 200
            except httpx.HTTPError:
                ok = False
            latencies.append((time.perf_counter() - start) * 1000)
        if not ok:
            errors += 1

    await asyncio.gather(*(one() for _ in range(requests)))
    latencies.sort()
    return Result(path, requests, errors, percentile(latencies, 50), percentile(latencies, 95))


async def run(
    base_url: str,
    *,
    requests: int,
    concurrency: int,
    session: str | None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> list[Result]:
    paths = PUBLIC_PATHS + (AUTHED_PATHS if session else ())
    cookies = {COOKIE_NAME: session} if session else None
    async with httpx.AsyncClient(
        base_url=base_url, cookies=cookies, timeout=10, transport=transport
    ) as client:
        return [await run_path(client, path, requests, concurrency) for path in paths]


def evaluate(results: list[Result], *, max_p95_ms: float, max_error_rate: float) -> list[str]:
    """합격선을 넘은 항목의 설명을 돌려준다. 비어 있으면 통과."""
    failures = []
    for r in results:
        if r.error_rate > max_error_rate:
            failures.append(f"{r.path}: 오류율 {r.error_rate:.1%} > {max_error_rate:.1%}")
        if r.p95_ms > max_p95_ms:
            failures.append(f"{r.path}: p95 {r.p95_ms:.0f}ms > {max_p95_ms:.0f}ms")
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="DEVON 로컬 서버 부하 스모크")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--requests", type=int, default=200, help="경로마다 보낼 요청 수")
    parser.add_argument("--concurrency", type=int, default=20)
    # 합격선은 임시값이다. 팀이 정하면 기본값을 바꾼다.
    parser.add_argument("--max-p95-ms", type=float, default=500)
    parser.add_argument("--max-error-rate", type=float, default=0.0)
    args = parser.parse_args(argv)

    session = os.environ.get("DEVON_SESSION") or None
    results = asyncio.run(
        run(args.base_url, requests=args.requests, concurrency=args.concurrency, session=session)
    )

    print(f"{'path':<16}{'requests':>10}{'errors':>8}{'p50(ms)':>10}{'p95(ms)':>10}")
    for r in results:
        print(f"{r.path:<16}{r.requests:>10}{r.errors:>8}{r.p50_ms:>10.1f}{r.p95_ms:>10.1f}")
    if not session:
        print("인증 경로는 DEVON_SESSION이 없어 측정하지 않았다.")

    failures = evaluate(results, max_p95_ms=args.max_p95_ms, max_error_rate=args.max_error_rate)
    for failure in failures:
        print("FAIL", failure)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
