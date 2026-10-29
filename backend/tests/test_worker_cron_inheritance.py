"""배포 worker가 부모의 추가 cron과 기존 분석 cron을 함께 보존한다."""

import importlib
from contextlib import contextmanager

import pytest
from arq import cron

from app.workers import analysis_app, arq_app
from app.workers.tasks.analysis_reaper import analysis_reaper


async def parent_job(ctx):
    pass


@pytest.fixture
def configured_parent(monkeypatch):
    @contextmanager
    def configured(jobs):
        try:
            with monkeypatch.context() as patch:
                patch.setattr(arq_app.WorkerSettings, "cron_jobs", jobs, raising=False)
                yield importlib.reload(analysis_app).WorkerSettings
        finally:
            importlib.reload(analysis_app)

    return configured


def test_deployment_worker_preserves_parent_cron_once(configured_parent):
    inherited = cron(parent_job, second={15, 45})
    with configured_parent([inherited]) as worker:
        assert worker.cron_jobs.count(inherited) == 1
        assert sum(job.coroutine is analysis_reaper for job in worker.cron_jobs) == 1
        assert {function.__name__ for function in worker.functions} >= {
            "initial_sync",
            "analysis_run",
            "candidate_page_analyze",
        }


def test_empty_parent_keeps_the_existing_analysis_schedule(configured_parent):
    with configured_parent([]) as worker:
        assert len(worker.cron_jobs) == 1
        assert worker.cron_jobs[0].coroutine is analysis_reaper
        assert worker.cron_jobs[0].second == {0, 30}
        assert worker.cron_jobs[0].run_at_startup is True
