"""활성 score_criteria 와 report 실패 이력을 읽기 전용으로 점검한다(#206).

backend 에서 ``python -m scripts.check_score_criteria`` 로 실행한다. DB·Redis 를 쓰지 않고
읽기만 하므로 개발·스테이징·운영 어디서든 실행해 같은 형식의 결과를 이슈에 붙일 수 있다.
활성 행이 SCORE_KEYS 6개와 정확히 같고 rubric 이 "0"~"4" 키를 가질 때만 exit 0 이다.
report:fail:* 는 활성화 전에 실패한 면접의 재시도 대상이며 삭제하지 않는다.

활성화 절차(환경별로 같다. 시점은 평가 담당이 검수 후 정한다):
1. ``python -m scripts.seed_all`` 로 rubric 문구를 적용한다(신규 행은 is_active=FALSE).
2. 문구를 검수한다.
3. 6행을 한 트랜잭션에서 한 번에 켠다. 일부만 켜면 리포트 생성이 실패한다.
   UPDATE score_criteria SET is_active = TRUE, updated_at = now()
   WHERE score_key IN ('project_understanding', 'technical_reasoning', 'problem_solving',
                       'communication', 'contribution_clarity', 'company_job_fit');
4. 이 스크립트를 실행해 ok=true 와 활성 6개를 확인하고 결과를 #206 에 남긴다.
"""

import asyncio
import json
from collections.abc import Mapping

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings
from app.db.models.knowledge import ScoreCriterion
from app.db.models.report import SCORE_KEYS

LEVELS = {str(level) for level in range(5)}


def find_problems(active: Mapping[str, object]) -> list[str]:
    """활성 행 {score_key: rubric} 이 리포트 생성 조건을 만족하지 않는 이유 목록."""
    problems = []
    if missing := sorted(set(SCORE_KEYS) - set(active)):
        problems.append(f"missing active keys: {missing}")
    if extra := sorted(set(active) - set(SCORE_KEYS)):
        problems.append(f"unexpected active keys: {extra}")
    for key in sorted(set(active) & set(SCORE_KEYS)):
        rubric = active[key]
        if not isinstance(rubric, dict) or set(rubric) != LEVELS:
            problems.append(f"rubric levels of {key} are not exactly 0..4")
    return problems


async def check() -> dict[str, object]:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    redis = Redis.from_url(settings.redis_url)
    try:
        async with engine.connect() as db:
            rows = await db.execute(
                select(ScoreCriterion.score_key, ScoreCriterion.rubric).where(
                    ScoreCriterion.is_active
                )
            )
            active = {key: rubric for key, rubric in rows}
        fail_keys = sorted([key async for key in redis.scan_iter("report:fail:*")])
    finally:
        await engine.dispose()
        await redis.aclose()
    problems = find_problems(active)
    return {
        "ok": not problems,
        "environment": settings.app_env,
        "active_count": len(active),
        "active_keys": sorted(active),
        "problems": problems,
        "failed_report_count": len(fail_keys),
        "failed_report_keys": [k.decode() if isinstance(k, bytes) else k for k in fail_keys],
    }


def main() -> int:
    try:
        result = asyncio.run(check())
    except Exception:
        print("점검 실패: DB·Redis 연결 설정을 확인하세요.")
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
