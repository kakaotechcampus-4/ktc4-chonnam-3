"""저장소 수집과 면접 준비 task를 같은 worker에 등록한다."""

from typing import Any

import httpx
from arq import cron, func
from arq.connections import RedisSettings
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.crypto import TokenCipher
from app.core.logging import configure_logging
from app.features.interview.prepare_lease import JOB_TIMEOUT_SECONDS
from app.features.profile.timeouts import PROFILE_JOB_TIMEOUT_SECONDS
from app.workers.tasks.initial_sync import initial_sync
from app.workers.tasks.interview_prep import interview_prep
from app.workers.tasks.interview_prep_reaper import interview_prep_reaper
from app.workers.tasks.interview_preparation_reaper import interview_preparation_reaper
from app.workers.tasks.profile_refresh_reaper import profile_refresh_reaper
from app.workers.tasks.profile_summary import profile_summary
from app.workers.tasks.report_generate import report_generate


async def startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    configure_logging(settings.log_level, json_logs=settings.is_prod or settings.log_json)
    settings.validate_auth()
    ctx["settings"] = settings
    ctx["engine"] = create_async_engine(settings.database_url, pool_pre_ping=True)
    ctx["session_factory"] = async_sessionmaker(ctx["engine"], expire_on_commit=False)
    ctx["cipher"] = TokenCipher(settings.token_encryption_key.get_secret_value())
    ctx["http_client"] = httpx.AsyncClient(timeout=15, follow_redirects=False)
    # ARQ의 job별 얕은 ctx 복사에서도 준비 복구 순회 상태를 공유한다.
    ctx.setdefault("preparation_scan_states", {})


async def shutdown(ctx: dict[str, Any]) -> None:
    await ctx["http_client"].aclose()
    await ctx["engine"].dispose()


class WorkerSettings:
    functions = [
        initial_sync,
        func(interview_prep, timeout=JOB_TIMEOUT_SECONDS),
        # 리포트의 영속 요청 만료와 맞추되 다른 작업의 기본 제한은 늘리지 않는다.
        func(report_generate, timeout=1800),
        func(profile_summary, timeout=PROFILE_JOB_TIMEOUT_SECONDS),
    ]
    cron_jobs = [
        cron(interview_preparation_reaper, second={0, 30}, run_at_startup=True),
        cron(interview_prep_reaper, second={0, 30}, run_at_startup=True),
        cron(profile_refresh_reaper, second={0, 30}, run_at_startup=True),
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_tries = 1
    job_timeout = 600
