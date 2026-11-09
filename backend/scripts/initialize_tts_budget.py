"""Cloud 잔여 무료량과 진행 중 호출을 확인한 운영자가 TTS 문자 예산을 초기화한다."""

import argparse
import asyncio
import re
import sys

from redis.asyncio import Redis

from app.core.config import get_settings
from app.features.interview.tts_budget import BudgetSnapshot, initialize_budget


async def initialize(
    project: str, monthly_limit: int, remaining_characters: int, period: str | None = None
) -> BudgetSnapshot:
    settings = get_settings()
    tts = settings.require_tts()
    # 다른 프로젝트·한도를 초기화해 실행 중인 서비스의 예산과 어긋나지 않게 한다.
    if tts.budget_project != project or tts.monthly_character_limit != monthly_limit:
        raise ValueError("TTS budget configuration mismatch")
    redis = Redis.from_url(settings.redis_url)
    try:
        return await initialize_budget(
            redis,
            project=project,
            monthly_limit=monthly_limit,
            remaining_characters=remaining_characters,
            period=period,
            basis="cloud_usage_confirmed",
        )
    finally:
        await redis.aclose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--period", help="미리 초기화할 UTC 연월 (YYYY-MM)")
    parser.add_argument("--monthly-limit", required=True, type=int)
    parser.add_argument("--remaining-characters", required=True, type=int)
    parser.add_argument(
        "--cloud-usage-confirmed",
        action="store_true",
        required=True,
        help="Cloud에서 다른 앱을 포함한 실제 잔여 무료량과 할당량을 확인했음",
    )
    parser.add_argument(
        "--no-inflight-confirmed",
        action="store_true",
        required=True,
        help="진행 중인 합성이 없으며 초기화 동안 새 합성을 막았음",
    )
    args = parser.parse_args(argv)
    if args.period is not None and not re.fullmatch(r"[0-9]{4}-(?:0[1-9]|1[0-2])", args.period):
        parser.error("period must be YYYY-MM")
    if not 0 < args.monthly_limit <= 1000000:
        parser.error("monthly-limit must be between 1 and 1000000")
    if not 0 <= args.remaining_characters <= args.monthly_limit:
        parser.error("remaining-characters must be between 0 and monthly-limit")
    if not args.project.strip() or len(args.project) > 256:
        parser.error("project is invalid")
    try:
        snapshot = asyncio.run(
            initialize(args.project, args.monthly_limit, args.remaining_characters, args.period)
        )
    except Exception:
        # 설정·연결 예외에는 키나 내부 URL이 섞일 수 있으므로 원문을 출력하지 않는다.
        print("TTS budget initialization failed. Check configuration and Redis.", file=sys.stderr)
        return 1
    print(
        f"period={snapshot.period} limit={snapshot.limit} "
        f"used={snapshot.used} remaining={snapshot.remaining}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
