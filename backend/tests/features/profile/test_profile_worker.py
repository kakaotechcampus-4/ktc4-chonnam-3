"""profile_summary worker: lock·실패 분리·이전 요약 유지. LLM 은 대역이다. task-16"""

import pytest

from app.llm_tasks import profile_summary as tasks
from app.workers.tasks import profile_summary as worker

from ..interview.factories import make_repo
from .fakes import LLM, ROLE, FakeGenerator, completed_interview, read_summary, refresh_summary


@pytest.fixture
def worker_env(app, monkeypatch):
    class _Settings:
        def require_llm(self):
            return LLM

    monkeypatch.setattr(worker, "get_settings", lambda: _Settings())
    return {
        "session_factory": app.state.session_factory,
        "http_client": None,
        "redis": app.state.redis,
    }


async def test_worker_runs_and_releases_lock(app, db, world, worker_env, monkeypatch):
    user, run = world
    repo = await make_repo(db, run, languages={"Python": 1})
    await completed_interview(db, run, [repo])
    generator = FakeGenerator()
    monkeypatch.setattr(tasks, "generate_role_summary", generator)
    await worker.profile_summary(worker_env, str(user.id))
    assert len(generator.calls) == 1
    assert (await read_summary(db, user)).role_summary == ROLE
    assert await app.state.redis.exists(f"profile:gen:{user.id}") == 0


async def test_worker_skips_when_lock_is_held(app, db, world, worker_env, monkeypatch):
    user, run = world
    repo = await make_repo(db, run, languages={"Python": 1})
    await completed_interview(db, run, [repo])
    generator = FakeGenerator()
    monkeypatch.setattr(tasks, "generate_role_summary", generator)
    await app.state.redis.set(f"profile:gen:{user.id}", "1", ex=600)
    await worker.profile_summary(worker_env, str(user.id))
    assert generator.calls == []
    assert await read_summary(db, user) is None
    assert await app.state.redis.exists(f"profile:gen:{user.id}") == 1


async def test_worker_failure_does_not_raise_and_keeps_summary(
    app, db, world, worker_env, monkeypatch
):
    user, run = world
    first = await make_repo(db, run, languages={"Python": 1})
    await completed_interview(db, run, [first])
    await refresh_summary(app, user, FakeGenerator())
    second = await make_repo(db, run, languages={"Java": 1})
    await completed_interview(db, run, [second])
    monkeypatch.setattr(tasks, "generate_role_summary", FakeGenerator(error=RuntimeError("boom")))
    await worker.profile_summary(worker_env, str(user.id))
    summary = await read_summary(db, user)
    assert summary.role_summary == ROLE
    assert summary.based_repo_ids == [first.id]
    assert await app.state.redis.exists(f"profile:gen:{user.id}") == 0


async def test_second_run_after_new_interview_refreshes_summary(
    app, db, world, worker_env, monkeypatch
):
    """같은 사용자의 두 번째 report 뒤 worker 가 다시 돌면 최신 저장소 집합으로 갱신된다."""
    user, run = world
    first = await make_repo(db, run, languages={"Python": 1})
    await completed_interview(db, run, [first])
    monkeypatch.setattr(tasks, "generate_role_summary", FakeGenerator())
    await worker.profile_summary(worker_env, str(user.id))
    assert (await read_summary(db, user)).based_repo_ids == [first.id]
    second = await make_repo(db, run, languages={"Java": 1})
    await completed_interview(db, run, [second])
    await worker.profile_summary(worker_env, str(user.id))
    summary = await read_summary(db, user)
    assert set(summary.based_repo_ids) == {first.id, second.id}
