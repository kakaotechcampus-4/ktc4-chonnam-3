"""실제 Director 호출의 단계·물리 시도와 중첩 실행 범위를 검증한다."""

import json
from uuid import uuid4

import httpx
import pytest
from devon_ai import contracts as c

from app.agents.director.runtime_adapter import execute_director
from app.core.config import Settings
from app.integrations.execution_ledger import ExecutionLedger, execution_scope, observe_call
from tests.agents.director_helpers import approved_review, plan, response, settings


async def test_nested_stages_link_physical_calls_and_restore_parent_scope(tmp_path):
    ledger = ExecutionLedger(tmp_path / "calls.sqlite3")
    with execution_scope(ledger, run_id="run", entrypoint="test"):
        async with observe_call("answer", kind="stage") as root:
            async with observe_call("plan", kind="stage") as child:
                async with observe_call("director") as attempt:
                    attempt.response(
                        {"model": "fixture", "usage": {"input_tokens": 7, "output_tokens": 3}}
                    )
            async with observe_call("review", kind="stage"):
                pass
    rows = {item.operation: item for item in ledger.records()}
    assert rows["plan"].parent_call_id == root.record.call_id
    assert rows["director"].parent_call_id == child.record.call_id
    assert rows["review"].parent_call_id == root.record.call_id
    assert rows["answer"].parent_call_id is None
    assert rows["director"].input_tokens == 7


async def test_interview_entrypoint_records_plan_review_and_two_physical_calls(tmp_path):
    from app.features.interview.observation import interview_execution

    path = tmp_path / "calls.sqlite3"
    config = Settings(_env_file=None, ai_execution_ledger_path=str(path))
    ctx = c.Context(
        "interview",
        None,
        1,
        9,
        (),
        ("hr_manager",),
        (),
        (),
        (),
        None,
        (),
        (),
        c.ContextLimits(2, 0, "test"),
    )
    outputs = iter((plan(), approved_review()))

    def handle(request):
        return response(next(outputs))

    from app.integrations.llm.client import CallBudget

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        async with interview_execution(config, "ws.answer", uuid4(), turn=1):
            result = await execute_director(
                ctx,
                prompt=c.PromptSpec("director", "director_v2", "fixture-model", "fixture"),
                settings=settings(),
                budget=CallBudget(),
                http_client=http,
            )
    assert result.succeeded
    rows = ExecutionLedger(path).records()
    physical = [item for item in rows if item.kind == "generation"]
    assert len(physical) == 2
    assert {item.operation for item in rows if item.kind == "stage"} >= {
        "ws.answer",
        "director.plan",
        "director.review",
    }
    assert all(item.parent_call_id for item in physical)
    assert all("interview_id" in item.metadata for item in rows)
    assert "fixture-key" not in json.dumps([item.metadata for item in rows])


async def test_ledger_initialization_does_not_block_the_event_loop(tmp_path, monkeypatch):
    import threading

    from app.features.interview import observation

    original = observation.ExecutionLedger
    threads = []
    main_thread = threading.get_ident()

    def construct(path):
        threads.append(threading.get_ident())
        return original(path)

    monkeypatch.setattr(observation, "ExecutionLedger", construct)
    config = Settings(_env_file=None, ai_execution_ledger_path=str(tmp_path / "calls.sqlite3"))
    async with observation.interview_execution(config, "ws.answer", uuid4(), turn=1):
        pass
    assert threads and all(thread != main_thread for thread in threads)


def test_finished_attempt_cannot_change_its_started_parent(tmp_path):
    from dataclasses import replace

    from app.integrations.execution_ledger import CallRecord

    ledger = ExecutionLedger(tmp_path / "calls.sqlite3")
    started = CallRecord(
        "child", "run", "test", "director", "generation", 1, parent_call_id="parent"
    )
    ledger.start(started)
    with pytest.raises(ValueError, match="identity"):
        ledger.finish(
            replace(started, status="succeeded", parent_call_id="other", elapsed_seconds=1)
        )


async def test_disabled_observation_does_not_create_files(tmp_path):
    from app.features.interview.observation import interview_execution

    async with interview_execution(Settings(_env_file=None), "ws.answer", uuid4(), turn=1):
        async with observe_call("director") as item:
            assert item is None
    assert list(tmp_path.iterdir()) == []
