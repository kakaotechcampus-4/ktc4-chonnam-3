"""선행 인증 워커 설정에 Task 11 작업만 추가한다."""

from typing import Any

from arq import cron

from app.core.config import get_settings
from app.workers.arq_app import WorkerSettings as InitialWorkerSettings
from app.workers.arq_app import startup as initial_startup
from app.workers.tasks.analysis_reaper import analysis_reaper
from app.workers.tasks.analysis_run import analysis_run
from app.workers.tasks.candidate_page_analyze import candidate_page_analyze


async def startup(ctx: dict[str, Any]) -> None:
    # DB·암호화·HTTP 자원 수명 주기는 #57의 기존 startup/shutdown을 따른다.
    await initial_startup(ctx)
    ctx["settings"] = get_settings()


class WorkerSettings(InitialWorkerSettings):
    # ARQ가 작업별로 서로 다른 인자 목록을 전달하므로 초기 수집 함수 타입으로 한정하지 않는다.
    functions: list[Any] = [*InitialWorkerSettings.functions, analysis_run, candidate_page_analyze]
    cron_jobs = [cron(analysis_reaper, second={0, 30}, run_at_startup=True)]
    on_startup = startup
    max_tries = 1
    keep_result = 0
