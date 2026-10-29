"""준비의 실패 단계 재개와 설정 오류가 실제 저장 상태에 맞는지 검사한다."""

import pytest
from sqlalchemy import select

from app.db.models import InterviewSession, RepoAnalysis, ScoreCriterion
from app.features.interview.service import retry_prepare
from tests.agents.test_director_prepare import Transport, run
from tests.agents.test_director_prepare import ready as ready


class Broker:
    def __init__(self):
        self.jobs = []

    async def enqueue_job(self, *args):
        self.jobs.append(args)


async def test_compose_retry_reuses_completed_sources_and_context(agent_sessions, ready):
    failed = Transport(ready)
    failed.outputs[0]["question"]["text"] = ""
    assert not await run(agent_sessions, ready, failed)
    async with agent_sessions() as db:
        row = await db.get(InterviewSession, ready["interview_id"])
        state = row.context_state["preparation_checkpoint"]
        assert state["completed"] == 3
        assert state["persona_context"]["counts"] == {
            "tech_lead": 0,
            "domain_lead": 0,
            "hr_manager": 0,
        }
        assert state["criteria_context"]["criteria"]
        await retry_prepare(
            db, Broker(), user_id=ready["owner"], interview_id=ready["interview_id"]
        )
    retried = Transport(ready)
    assert await run(agent_sessions, ready, retried)
    assert retried.github == []
    assert retried.model_operations == ["plan", "review"]
    async with agent_sessions() as db:
        row = await db.get(InterviewSession, ready["interview_id"])
        assert row.context_state["preparation_checkpoint"] == state


async def test_changed_completed_criteria_rejects_resume_without_external_io(agent_sessions, ready):
    failed = Transport(ready)
    failed.outputs[0]["question"]["text"] = ""
    assert not await run(agent_sessions, ready, failed)
    async with agent_sessions() as db:
        criterion = await db.scalar(select(ScoreCriterion).limit(1))
        criterion.rubric = {"changed": True}
        await db.commit()
        await retry_prepare(
            db, Broker(), user_id=ready["owner"], interview_id=ready["interview_id"]
        )
    retried = Transport(ready)
    assert not await run(agent_sessions, ready, retried)
    assert retried.github == [] and retried.model_operations == []
    async with agent_sessions() as db:
        row = await db.get(InterviewSession, ready["interview_id"])
        assert row.last_error["code"] == "preparation_inputs_changed"


@pytest.mark.parametrize(
    "phase, expected", [("initialize_personas", 1), ("initialize_criteria", 2)]
)
async def test_middle_phase_retry_keeps_prior_success(
    agent_sessions, ready, monkeypatch, phase, expected
):
    from app.features.interview import prepare_checkpoint
    from app.features.interview.repository_sources import SourcePreparationError

    original = getattr(prepare_checkpoint, phase)

    async def unavailable(*args):
        raise SourcePreparationError("phase_temporarily_unavailable")

    monkeypatch.setattr(prepare_checkpoint, phase, unavailable)
    assert not await run(agent_sessions, ready, Transport(ready))
    async with agent_sessions() as db:
        row = await db.get(InterviewSession, ready["interview_id"])
        assert row.context_state["preparation_checkpoint"]["completed"] == expected
        assert [s["status"] for s in row.prepare_steps][:expected] == ["completed"] * expected
        await retry_prepare(db, Broker(), user_id=ready["owner"], interview_id=row.id)
    monkeypatch.setattr(prepare_checkpoint, phase, original)
    retried = Transport(ready)
    assert await run(agent_sessions, ready, retried)
    assert retried.github == [] and retried.model_operations == ["plan", "review"]


async def test_actual_deployment_worker_keeps_all_jobs_and_reaper():
    from app.workers.analysis_app import WorkerSettings
    from app.workers.tasks.interview_prep import interview_prep

    assert WorkerSettings.functions.count(interview_prep) == 1
    assert {f.__name__ for f in WorkerSettings.functions} >= {
        "initial_sync",
        "analysis_run",
        "candidate_page_analyze",
        "interview_prep",
    }
    assert "analysis_reaper" in {job.coroutine.__name__ for job in WorkerSettings.cron_jobs}
    assert "interview_preparation_reaper" in {
        job.coroutine.__name__ for job in WorkerSettings.cron_jobs
    }
    assert WorkerSettings.max_tries == 1
    assert WorkerSettings.job_timeout == 600


async def test_changed_criteria_during_director_is_not_stored(agent_sessions, ready):
    transport = Transport(ready)
    changed = False

    async def replace(request):
        nonlocal changed
        if request.method == "POST" and not changed:
            changed = True
            async with agent_sessions.begin() as db:
                criterion = await db.scalar(select(ScoreCriterion).limit(1))
                criterion.rubric = {"changed_during_director": True}
        return await transport(request)

    assert not await run(agent_sessions, ready, replace)
    from app.db.models import InterviewTurn, LLMCallRecord

    async with agent_sessions() as db:
        assert (await db.scalars(select(InterviewTurn))).all() == []
        record = await db.scalar(select(LLMCallRecord).where(LLMCallRecord.task_name == "director"))
        assert record.discard_reason == "context_changed" and len(record.attempts) == 2
        row = await db.get(InterviewSession, ready["interview_id"])
        assert row.last_error["code"] == "preparation_inputs_changed"
        assert row.last_error["recoverable"] is False


async def test_other_sha_analyses_do_not_invalidate_completed_preparation(agent_sessions, ready):
    failed = Transport(ready)
    failed.outputs[0]["question"]["text"] = ""
    assert not await run(agent_sessions, ready, failed)
    async with agent_sessions.begin() as db:
        for level in ("l1", "l2"):
            original = await db.scalar(
                select(RepoAnalysis).where(RepoAnalysis.analysis_level == level)
            )
            db.add(
                RepoAnalysis(
                    repository_id=original.repository_id,
                    analysis_level=level,
                    status="succeeded",
                    head_sha="d" * 40,
                    model=original.model,
                    prompt_version=original.prompt_version,
                    result={"new_run": True},
                )
            )
    async with agent_sessions() as db:
        await retry_prepare(
            db, Broker(), user_id=ready["owner"], interview_id=ready["interview_id"]
        )
    retried = Transport(ready)
    assert await run(agent_sessions, ready, retried)
    assert retried.github == [] and retried.model_operations == ["plan", "review"]


async def test_configuration_error_on_compose_retry_preserves_completed_steps(
    agent_sessions, ready
):
    import httpx

    from app.features.interview.prepare import prepare_interview
    from tests.agents.test_director_prepare import settings

    failed = Transport(ready)
    failed.outputs[0]["question"]["text"] = ""
    assert not await run(agent_sessions, ready, failed)
    async with agent_sessions() as db:
        await retry_prepare(
            db, Broker(), user_id=ready["owner"], interview_id=ready["interview_id"]
        )
    retried = Transport(ready)
    async with httpx.AsyncClient(transport=httpx.MockTransport(retried)) as http:
        assert not await prepare_interview(
            agent_sessions,
            user_id=ready["owner"],
            interview_id=ready["interview_id"],
            settings=settings().model_copy(update={"openai_api_key": None}),
            http_client=http,
        )
    async with agent_sessions() as db:
        row = await db.get(InterviewSession, ready["interview_id"])
        assert [step["status"] for step in row.prepare_steps] == ["completed"] * 3 + ["failed"]
        assert row.last_error["step"] == "compose_question"
    assert retried.github == [] and retried.model_operations == []
