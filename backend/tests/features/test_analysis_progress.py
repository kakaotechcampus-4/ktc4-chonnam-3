"""API·신규 migration 없이 기존 상태 계약과 DB commit 이후 알림을 검증한다."""

import json
from pathlib import Path
from uuid import uuid4

import pytest
import yaml
from pydantic import ValidationError
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models.analysis import AnalysisJob
from app.db.models.user import User
from app.features.analysis.pipeline.run_state import set_step
from app.features.analysis.run_status import initial_steps, status_response


@pytest.mark.parametrize("has_document", [False, True])
def test_initial_steps_keep_all_seven_steps_and_only_skip_absent_document(has_document):
    steps = initial_steps(has_document)
    assert [item["key"] for item in steps] == [
        "doc_extract",
        "repo_select",
        "repo_detail",
        "jd_fetch",
        "jd_extract",
        "repo_analyze",
        "match_score",
    ]
    assert steps[0]["status"] == ("pending" if has_document else "skipped")
    assert all(item["status"] == "pending" for item in steps[1:])


@pytest.mark.parametrize(
    "status,expected", [("running", "running"), ("partial", "failed"), ("succeeded", "completed")]
)
def test_status_preserves_existing_openapi_and_internal_failure_code(status, expected):
    steps = initial_steps(False)
    steps[1]["status"] = steps[2]["status"] = "completed"
    run = AnalysisJob(
        id=uuid4(), status=status, steps=steps, error_code="token_invalid", estimated_seconds=None
    )
    payload = status_response(run).model_dump(mode="json")
    path = Path(__file__).resolve().parents[3] / "spec/shared/contracts/openapi.yaml"
    schema = yaml.safe_load(path.read_text(encoding="utf-8"))["components"]["schemas"][
        "AnalysisRunResponse"
    ]
    assert set(payload) == set(schema["required"])
    assert payload["status"] == expected
    assert payload["progress"] == 33
    assert payload["failureReason"] == "token_invalid"
    assert len(payload["steps"]) == 7


def test_missing_steps_are_skipped_without_dividing_by_zero():
    run = AnalysisJob(
        id=uuid4(), status="failed", steps=[], error_code=None, estimated_seconds=None
    )
    payload = status_response(run).model_dump(mode="json")
    assert payload["progress"] == 0
    assert all(step["status"] == "skipped" for step in payload["steps"])


@pytest.mark.parametrize("field", ["analysis_run_ttl_seconds", "repo_candidate_limit"])
@pytest.mark.parametrize("value", [0, -1])
def test_existing_limits_require_positive_values(field, value):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{field: value})


@pytest.fixture
async def progress_run(db):
    user = User(name="진행 상태 검증")
    db.add(user)
    await db.flush()
    run = AnalysisJob(
        user_id=user.id, job_type="analysis_run", status="running", steps=initial_steps(False)
    )
    db.add(run)
    await db.commit()
    return run.id


def _context(app):
    return {
        "session_factory": app.state.session_factory,
        "redis": app.state.redis,
        "settings": app.state.settings,
    }


async def test_step_commit_is_visible_before_full_mirror_ttl_and_publish(
    app, progress_run, monkeypatch
):
    redis = app.state.redis
    original = redis.pipeline
    observed = []

    def pipeline(*args, **kwargs):
        pipe = original(*args, **kwargs)
        execute = pipe.execute

        async def after_commit(*args, **kwargs):
            # 외부 연결에서 저장 상태가 보이는 순간에만 알림을 허용한다.
            async with app.state.session_factory() as db:
                run = await db.get(AnalysisJob, progress_run)
                observed.append(
                    (
                        {item["key"]: item["status"] for item in run.steps},
                        [cmd[0] for cmd, _ in pipe.command_stack],
                    )
                )
            return await execute(*args, **kwargs)

        pipe.execute = after_commit
        return pipe

    monkeypatch.setattr(redis, "pipeline", pipeline)
    expected = {item["key"]: item["status"] for item in initial_steps(False)}
    expected["repo_select"] = "running"
    async with redis.pubsub() as pubsub:
        await pubsub.subscribe(f"run:{progress_run}:events")
        await pubsub.get_message(timeout=1)
        await set_step(_context(app), progress_run, "repo_select", "running")
        message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1)
    assert message and json.loads(message["data"]) == {
        "type": "step",
        "step": "repo_select",
        "status": "running",
    }
    assert observed == [(expected, ["HSET", "EXPIRE", "PUBLISH"])]
    assert {
        k.decode(): v.decode()
        for k, v in (await redis.hgetall(f"run:{progress_run}:steps")).items()
    } == expected
    assert (
        0
        < await redis.ttl(f"run:{progress_run}:steps")
        <= app.state.settings.analysis_run_ttl_seconds
    )


async def test_rollback_never_mirrors_uncommitted_step(app, progress_run):
    def reject_commit(session):
        raise RuntimeError("fixture commit failure")

    event.listen(Session, "before_commit", reject_commit)
    try:
        with pytest.raises(RuntimeError, match="fixture commit failure"):
            await set_step(_context(app), progress_run, "repo_select", "running")
    finally:
        event.remove(Session, "before_commit", reject_commit)
    async with app.state.session_factory() as db:
        run = await db.get(AnalysisJob, progress_run)
        assert run.steps == initial_steps(False)
    assert not await app.state.redis.exists(f"run:{progress_run}:steps")


async def test_notification_failure_keeps_committed_step(app, progress_run, monkeypatch):
    def unavailable(*args, **kwargs):
        raise ConnectionError("fixture Redis failure")

    monkeypatch.setattr(app.state.redis, "pipeline", unavailable)
    await set_step(_context(app), progress_run, "repo_select", "running")
    async with app.state.session_factory() as db:
        run = await db.get(AnalysisJob, progress_run)
        assert (
            next(item for item in run.steps if item["key"] == "repo_select")["status"] == "running"
        )


async def test_terminal_stream_uses_existing_data_type_key_contract(app, progress_run):
    # SSE 기반은 Task 12의 실제 구현을 사용하며 대체 이벤트 구현을 만들지 않는다.
    from app.features.analysis.stream import analysis_events

    async with app.state.session_factory() as db:
        run = await db.get(AnalysisJob, progress_run)
        user_id = run.user_id
        run.status, run.error_code = "failed", "jd_fetch_failed"
        run.steps = [
            {**item, "status": "failed" if item["key"] == "jd_fetch" else "skipped"}
            for item in run.steps
        ]
        await db.commit()
    frames = [
        frame
        async for frame in analysis_events(
            app.state.session_factory, app.state.redis, progress_run, user_id
        )
    ]
    assert all(set(frame) == {"data"} for frame in frames)
    values = [json.loads(frame["data"]) for frame in frames]
    assert values[-1] == {"type": "failed", "reason": "jd_fetch_failed"}
    steps = [value for value in values if value["type"] == "step"]
    assert len(steps) == 7 and all("key" in value and "step" not in value for value in steps)
    assert {"type": "progress", "value": 0} in values
