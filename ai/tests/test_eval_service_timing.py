"""서비스 실패·취소 시간도 기록하고 Judge 시간은 분리한다."""

import asyncio

import pytest
from async_grader import content_hash
from eval_cases import Case
from eval_runner import Execution, ExecutionError, run_cases


def fixture():
    return Case(
        "q-timing",
        1,
        "question",
        "dev",
        "timing-group",
        {},
        {
            "allowed": [],
            "forbidden": [],
            "grader_controls": [],
            "review": {"status": "unreviewed", "reviewer": None},
        },
    )


def test_failed_execution_keeps_elapsed_service_time(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr("eval_runner.time.perf_counter", lambda: clock[0])

    async def execute(kind, payload):
        clock[0] += 2
        raise ExecutionError("semantic", "rejected")

    row = asyncio.run(run_cases([fixture()], execute, metadata={}))["cases"][0]
    assert row["status"] == "failed"
    assert row["service_latency_ms"] == 2000


def test_judge_time_is_excluded_from_successful_service_time(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr("eval_runner.time.perf_counter", lambda: clock[0])

    async def execute(kind, payload):
        clock[0] += 2
        return Execution({"question": "candidate"})

    async def judge(rubric, output):
        clock[0] += 20
        return "accept"

    row = asyncio.run(
        run_cases([fixture()], execute, metadata={}, grader=judge, diagnostic_judge=True)
    )["cases"][0]
    assert row["service_latency_ms"] == 2000
    assert row["latency_ms"] == 22000


def test_cancellation_checkpoints_elapsed_service_time_then_propagates(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr("eval_runner.time.perf_counter", lambda: clock[0])
    saved = []

    async def execute(kind, payload):
        clock[0] += 2
        raise asyncio.CancelledError()

    async def checkpoint(document):
        saved.append(document)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(run_cases([fixture()], execute, metadata={}, checkpoint=checkpoint))
    assert saved[-1]["cases"] == []
    assert saved[-1]["checkpoint"] == {"completed": 0, "total": 1, "current_case": "q-timing.v1"}
    inflight = saved[-1]["inflight_case"]
    assert inflight["status"] == "interrupted"
    assert inflight["service_latency_ms"] == 2000
    assert inflight["error_code"] == "CancelledError"
    assert inflight["service_status"] == "interrupted"
    assert inflight["interrupted_stage"] == "service"


def test_judge_cancellation_keeps_service_output_usage_and_time_without_completing_case(
    monkeypatch,
):
    clock = [100.0]
    monkeypatch.setattr("eval_runner.time.perf_counter", lambda: clock[0])
    saved = []
    case = fixture()
    case.payload.update(
        service_task="director", service_input={"context": {"interview_id": "session"}}
    )
    model_payload = {"operation": "plan", "context": {"interview_id": "session"}}
    snapshot = {
        "schema_version": "director-model-sources.v1",
        "service_input_sha256": content_hash(case.payload),
        "requests": [
            {
                "operation": "plan",
                "prompt_version": "director_v9",
                "model": "fixture-model",
                "schema_version": "director-plan.v3",
                "payload": model_payload,
                "payload_sha256": content_hash(model_payload),
            }
        ],
    }

    async def execute(kind, payload):
        clock[0] += 2
        return Execution(
            {"question": "candidate"},
            ({"input_tokens": 5, "output_tokens": 7},),
            source_snapshot=snapshot,
        )

    async def judge(rubric, output):
        clock[0] += 20
        raise asyncio.CancelledError()

    async def checkpoint(document):
        saved.append(document)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(
            run_cases(
                [case],
                execute,
                metadata={},
                checkpoint=checkpoint,
                grader=judge,
                diagnostic_judge=True,
            )
        )
    assert saved[-1]["checkpoint"]["completed"] == 0
    inflight = saved[-1]["inflight_case"]
    assert inflight["output"] == {"question": "candidate"}
    assert inflight["input_tokens"] == 5 and inflight["output_tokens"] == 7
    assert inflight["service_latency_ms"] == 2000
    assert inflight["latency_ms"] == 22000
    assert inflight["service_status"] == "completed"
    assert inflight["interrupted_stage"] == "evaluation"
    assert inflight["source_snapshot"] == snapshot
    assert inflight["source_snapshot_hash"] == content_hash(snapshot)
