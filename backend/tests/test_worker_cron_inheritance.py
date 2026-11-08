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


@pytest.mark.parametrize("container", [list, tuple], ids=["list", "tuple"])
def test_deployment_worker_preserves_parent_cron_once(configured_parent, container):
    inherited = cron(parent_job, second={15, 45})
    with configured_parent(container([inherited])) as worker:
        assert worker.cron_jobs.count(inherited) == 1
        assert sum(job.coroutine is analysis_reaper for job in worker.cron_jobs) == 1
        assert {function.__name__ for function in worker.functions} >= {
            "initial_sync",
            "analysis_run",
            "candidate_page_analyze",
        }


@pytest.mark.parametrize("jobs", [[], (), None], ids=["list", "tuple", "none"])
def test_empty_parent_keeps_the_existing_analysis_schedule(configured_parent, jobs):
    with configured_parent(jobs) as worker:
        assert len(worker.cron_jobs) == 1
        assert worker.cron_jobs[0].coroutine is analysis_reaper
        assert worker.cron_jobs[0].second == {0, 30}
        assert worker.cron_jobs[0].run_at_startup is True


def test_parent_without_optional_cron_setting_preserves_arq_default(monkeypatch):
    try:
        with monkeypatch.context() as patch:
            patch.delattr(arq_app.WorkerSettings, "cron_jobs", raising=False)
            worker = importlib.reload(analysis_app).WorkerSettings
            assert len(worker.cron_jobs) == 1
            assert worker.cron_jobs[0].coroutine is analysis_reaper
    finally:
        importlib.reload(analysis_app)


def test_invalid_parent_cron_setting_is_not_treated_as_empty(configured_parent):
    with pytest.raises(TypeError):
        with configured_parent(0):
            pass
