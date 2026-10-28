"""report_generate worker: 성공 후 enqueue·실패 이력·lock 해제. LLM 은 대역이다. task-16"""

import copy

import pytest
from devon_ai import contracts as c
from sqlalchemy import func, select

from app.db.models import InterviewReport, PromptVersion, ReportScore
from app.features.report import service
from app.llm_tasks.report import ReportDraftInvalidError, ReportModuleUnavailableError
from app.workers.tasks import report_generate as worker

from .fakes import LLM, OUTPUT, FakeGenerator


@pytest.fixture
async def prompt(db):
    db.add(
        PromptVersion(
            task_name="report",
            version="fixture-v1",
            model="fixture-model",
            template="t",
            is_active=True,
        )
    )
    await db.commit()


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


async def test_worker_failure_records_history_and_releases_lock(
    app, db, ctx, prompt, worker_env, enqueue, monkeypatch
):
    interview, _ = ctx
    _use(monkeypatch, FakeGenerator(output=_bad(lambda d: d["scores"].pop("communication"))))
    await app.state.redis.set(f"report:gen:{interview.id}", "1")
    await worker.report_generate(worker_env, str(interview.id))
    assert await _counts(db) == (0, 0)
    assert await app.state.redis.exists(f"report:gen:{interview.id}") == 0
    assert await app.state.redis.get(f"report:fail:{interview.id}") in (
        b"report_invalid",
        "report_invalid",
    )
    enqueue.assert_not_awaited()


async def test_worker_without_ai_module_records_failure(
    app, db, ctx, prompt, worker_env, enqueue, monkeypatch
):
    interview, _ = ctx
    # 실제 resolve_generator 를 그대로 쓴다. AI 모듈에 generate_report 가 아직 없다.
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


def test_failure_codes_are_stable():
    assert service.failure_code(ReportModuleUnavailableError("x")) == "report_module_unavailable"
    assert service.failure_code(ReportDraftInvalidError("x")) == "report_invalid"
    assert service.failure_code(c.ContractError("schema", "x")) == "llm_failed"
    assert service.failure_code(RuntimeError("x")) == "internal_error"
