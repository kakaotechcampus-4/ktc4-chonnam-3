"""ARQ WorkerSettings — 큐 정의, 재시도, 타임아웃.

이번 범위에서 등록하는 태스크 3종 —
  initial_sync           GitHub 연동 직후 public repo L0-a 수집 (repo_sync)
  analysis_run           공고 입력 후 7 step 분석
  candidate_page_analyze '더 보기' page 분석

interview_prep / deep_analysis / report_generate 는 해당 task 에서 등록한다.

docs/pipeline.md 1절 / task-11
"""

from typing import Any

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import get_sessionmaker
from app.workers.tasks.analysis_run import analysis_run
from app.workers.tasks.candidate_page_analyze import candidate_page_analyze
from app.workers.tasks.initial_sync import initial_sync


def build_redis_settings() -> RedisSettings:
    """API 와 worker 가 같은 Redis 를 본다."""
    return RedisSettings.from_dsn(get_settings().redis_url)


async def create_arq_pool() -> ArqRedis:
    """FastAPI lifespan 에서 쓰는 enqueue 전용 pool."""
    return await create_pool(build_redis_settings())


async def startup(ctx: dict[str, Any]) -> None:
    configure_logging()
    ctx["sessionmaker"] = get_sessionmaker()


async def shutdown(ctx: dict[str, Any]) -> None:
    ctx.pop("sessionmaker", None)


class WorkerSettings:
    """`arq app.workers.arq_app.WorkerSettings` 로 실행한다."""

    functions = [analysis_run, initial_sync, candidate_page_analyze]
    redis_settings = build_redis_settings()
    on_startup = startup
    on_shutdown = shutdown
    max_tries = 2  # LLM/외부 호출 실패는 자동 1회 재시도
    job_timeout = 600
    keep_result = 3_600
