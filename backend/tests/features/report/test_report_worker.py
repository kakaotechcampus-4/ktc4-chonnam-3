"""report_generate worker: 성공 후 enqueue·실패 이력·lock 해제. LLM 은 대역이다. task-16"""

import copy

import pytest
from devon_ai import contracts as c
from sqlalchemy import func, select, update

from app.db.models import InterviewReport, ReportScore, ScoreCriterion
from app.features.report import service
from app.llm_tasks.report import (
    ReportDraftInvalidError,
    ReportModuleUnavailableError,
    ReportRubricUnavailableError,
)
from app.workers.tasks import report_generate as worker

from .fakes import LLM, OUTPUT, FakeGenerator


async def _counts(db):
    reports = await db.scalar(select(func.count()).select_from(InterviewReport))
    scores = await db.scalar(select(func.count()).select_from(ReportScore))
    return reports, scores


def _bad(mutate):
    data = copy.deepcopy(OUTPUT)
    mutate(data)
    return data


@pytest.fixture
def worker_env(app, monkeypatch, enqueue):
    """worker 가 쓰는 설정과 http client 를 대체한다. enqueue 는 report 라우터 fixture 와 같다."""

    class _Settings:
        def require_llm(self):
            return LLM

    monkeypatch.setattr(worker, "get_settings", lambda: _Settings())
    return {
        "session_factory": app.state.session_factory,
        "http_client": None,
        "redis": app.state.redis,
    }


def _use(monkeypatch, generator):
    monkeypatch.setattr(service, "resolve_generator", lambda: generator)


async def test_worker_success_enqueues_profile_summary_and_releases_lock(
    app, db, ctx, prompt, worker_env, enqueue, monkeypatch
):
    interview, _ = ctx
    _use(monkeypatch, FakeGenerator())
    await app.state.redis.set(f"report:gen:{interview.id}", "1")
    await worker.report_generate(worker_env, str(interview.id))
    assert await _counts(db) == (1, 6)
    assert await app.state.redis.exists(f"report:gen:{interview.id}") == 0
    assert await app.state.redis.exists(f"report:fail:{interview.id}") == 0
    enqueue.assert_awaited_once_with(
        "profile_summary",
        str(interview.user_id),
        _job_id=f"profile_summary:{interview.user_id}",
    )


async def test_worker_failure_records_history_and_keeps_lock(
    app, db, ctx, prompt, worker_env, enqueue, monkeypatch
):
    interview, _ = ctx
    _use(monkeypatch, FakeGenerator(output=_bad(lambda d: d["scores"].pop("communication"))))
    await app.state.redis.set(f"report:gen:{interview.id}", "1")
    await worker.report_generate(worker_env, str(interview.id))
    assert await _counts(db) == (0, 0)
    # 실패 후에는 lock TTL 이 냉각 시간이라 폴링이 바로 재enqueue 하지 못한다.
    assert await app.state.redis.exists(f"report:gen:{interview.id}") == 1
    assert await app.state.redis.get(f"report:fail:{interview.id}") in (
        b"report_invalid",
        "report_invalid",
    )
    enqueue.assert_not_awaited()


async def test_worker_skipped_releases_lock(app, db, ctx, prompt, worker_env, enqueue, monkeypatch):
    interview, _ = ctx
    interview.status = "abandoned"
    await db.commit()
    _use(monkeypatch, FakeGenerator())
    await app.state.redis.set(f"report:gen:{interview.id}", "1")
    await worker.report_generate(worker_env, str(interview.id))
    assert await app.state.redis.exists(f"report:gen:{interview.id}") == 0
    assert await app.state.redis.exists(f"report:fail:{interview.id}") == 0
    enqueue.assert_not_awaited()


async def test_worker_without_ai_module_records_failure(
    app, db, ctx, prompt, worker_env, enqueue, monkeypatch
):
    interview, _ = ctx
    # AI 모듈에 generate_report 가 없는 상태를 만든다(병합 뒤에도 실패 경로를 확인한다).
    monkeypatch.delattr("devon_ai.llm_tasks.report.generate_report", raising=False)
    await worker.report_generate(worker_env, str(interview.id))
    assert await app.state.redis.get(f"report:fail:{interview.id}") in (
        b"report_module_unavailable",
        "report_module_unavailable",
    )
    enqueue.assert_not_awaited()


async def test_enqueue_failure_keeps_report(app, db, ctx, prompt, worker_env, enqueue, monkeypatch):
    interview, _ = ctx
    _use(monkeypatch, FakeGenerator())
    enqueue.side_effect = RuntimeError("redis down")
    await worker.report_generate(worker_env, str(interview.id))
    assert await _counts(db) == (1, 6)
    assert await app.state.redis.exists(f"report:fail:{interview.id}") == 0


async def test_worker_rerun_after_success_does_not_enqueue_again(
    app, db, ctx, prompt, worker_env, enqueue, monkeypatch
):
    interview, _ = ctx
    generator = FakeGenerator()
    _use(monkeypatch, generator)
    await worker.report_generate(worker_env, str(interview.id))
    await worker.report_generate(worker_env, str(interview.id))
    assert len(generator.calls) == 1
    assert enqueue.await_count == 1


async def test_worker_without_active_rubrics_records_failure(
    app, db, ctx, prompt, worker_env, enqueue, monkeypatch
):
    interview, _ = ctx
    await db.execute(update(ScoreCriterion).values(is_active=False))
    await db.commit()
    _use(monkeypatch, FakeGenerator())
    await worker.report_generate(worker_env, str(interview.id))
    failure = await app.state.redis.get(f"report:fail:{interview.id}")
    assert failure in (b"report_rubric_unavailable", "report_rubric_unavailable")
    assert await _counts(db) == (0, 0)
    enqueue.assert_not_awaited()


def test_failure_codes_are_stable():
    assert service.failure_code(ReportRubricUnavailableError("x")) == "report_rubric_unavailable"
    assert service.failure_code(ReportModuleUnavailableError("x")) == "report_module_unavailable"
    assert service.failure_code(ReportDraftInvalidError("x")) == "report_invalid"
    assert service.failure_code(c.ContractError("schema", "x")) == "llm_failed"
    assert (
        service.failure_code(c.ContractError("semantic", "unscorable key"))
        == "report_unscorable_key"
    )
    assert service.failure_code(RuntimeError("x")) == "internal_error"
