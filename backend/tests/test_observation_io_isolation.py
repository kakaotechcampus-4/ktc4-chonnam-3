"""선택적인 서비스 장부 I/O만 격리하고 실제 처리·strict 평가·취소를 보존한다."""

import asyncio
import sqlite3
import threading
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.features.interview import observation
from app.integrations.execution_ledger import ExecutionLedger, execution_scope, observe_call
from app.integrations.llm import client
from tests.integrations.test_llm_client import request, response, validate

IO_ERRORS = [OSError, sqlite3.OperationalError]


@pytest.mark.parametrize("error_type", IO_ERRORS)
async def test_service_continues_when_optional_ledger_initialization_fails(
    tmp_path, monkeypatch, caplog, error_type
):
    def broken(_path):
        raise error_type("private path must not appear in logs")

    monkeypatch.setattr(observation, "ExecutionLedger", broken)
    config = Settings(_env_file=None, ai_execution_ledger_path=str(tmp_path / "calls.sqlite3"))
    async with observation.interview_execution(config, "ws.answer", uuid4()) as observed:
        assert observed is None
        async with observe_call("director") as nested:
            assert nested is None
    assert "ai_execution_ledger_io_failed" in caplog.text
    assert "private path" not in caplog.text


@pytest.mark.parametrize("phase", ["start", "finish"])
@pytest.mark.parametrize("error_type", IO_ERRORS)
async def test_optional_generation_io_error_preserves_successful_http_result_and_attempt(
    tmp_path, monkeypatch, caplog, phase, error_type
):
    original = getattr(ExecutionLedger, phase)

    def broken(self, record):
        if record.kind == "generation":
            raise error_type("private disk detail")
        return original(self, record)

    monkeypatch.setattr(ExecutionLedger, phase, broken)
    sent, attempts = [], []

    def handle(incoming):
        sent.append(incoming)
        return httpx.Response(200, json=response())

    config = Settings(_env_file=None, ai_execution_ledger_path=str(tmp_path / "calls.sqlite3"))
    async with observation.interview_execution(config, "ws.answer", uuid4()):
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
            result = await client.call_model(
                request(),
                validate,
                api_key=SecretStr("fixture"),
                base_url="https://provider.fixture/v1",
                http_client=http,
                attempt_sink=attempts,
            )
    assert result.data == 7 and result.failure is None
    assert len(sent) == len(attempts) == 1
    assert attempts[0].input_tokens == 12 and attempts[0].output_tokens == 4
    assert "ai_execution_ledger_io_failed" in caplog.text
    assert "private disk detail" not in caplog.text
    rows = ExecutionLedger(tmp_path / "calls.sqlite3").records()
    physical = [row for row in rows if row.kind == "generation"]
    if phase == "start":
        assert physical == []
    else:
        assert len(physical) == 1 and physical[0].status == "started"


@pytest.mark.parametrize("phase", ["start", "finish"])
@pytest.mark.parametrize("error_type", IO_ERRORS)
async def test_default_evaluation_scope_still_raises_ledger_io_errors(
    tmp_path, monkeypatch, phase, error_type
):
    ledger = ExecutionLedger(tmp_path / "calls.sqlite3")

    def broken(self, record):
        raise error_type("strict audit unavailable")

    monkeypatch.setattr(ExecutionLedger, phase, broken)
    with pytest.raises(error_type, match="strict audit unavailable"):
        with execution_scope(ledger, run_id="strict", entrypoint="evaluation_cli"):
            async with observe_call("director"):
                pass


@pytest.mark.parametrize("error", [RuntimeError("business failure"), asyncio.CancelledError()])
async def test_optional_finish_io_error_does_not_replace_original_error(
    tmp_path, monkeypatch, error
):
    def broken(self, record):
        raise sqlite3.OperationalError("disk full")

    monkeypatch.setattr(ExecutionLedger, "finish", broken)
    config = Settings(_env_file=None, ai_execution_ledger_path=str(tmp_path / "calls.sqlite3"))
    with pytest.raises(type(error)) as caught:
        async with observation.interview_execution(config, "ws.answer", uuid4()):
            raise error
    assert caught.value is error


@pytest.mark.parametrize("phase", ["start", "finish"])
@pytest.mark.parametrize(
    "error_type", [TypeError, sqlite3.ProgrammingError, sqlite3.IntegrityError]
)
async def test_service_does_not_hide_ledger_programming_errors(
    tmp_path, monkeypatch, phase, error_type
):
    def broken(self, record):
        raise error_type("incorrect ledger implementation")

    monkeypatch.setattr(ExecutionLedger, phase, broken)
    config = Settings(_env_file=None, ai_execution_ledger_path=str(tmp_path / "calls.sqlite3"))
    with pytest.raises(error_type, match="incorrect ledger implementation"):
        async with observation.interview_execution(config, "ws.answer", uuid4()):
            pass


@pytest.mark.parametrize("error_type", [TypeError, sqlite3.ProgrammingError])
async def test_service_does_not_hide_initialization_programming_errors(
    tmp_path, monkeypatch, error_type
):
    def broken(_path):
        raise error_type("incorrect ledger initialization")

    monkeypatch.setattr(observation, "ExecutionLedger", broken)
    config = Settings(_env_file=None, ai_execution_ledger_path=str(tmp_path / "calls.sqlite3"))
    with pytest.raises(error_type, match="incorrect ledger initialization"):
        async with observation.interview_execution(config, "ws.answer", uuid4()):
            pass


async def test_service_does_not_hide_validator_error_when_finish_io_fails(tmp_path, monkeypatch):
    def broken(self, record):
        raise sqlite3.OperationalError("disk full")

    def invalid(_raw):
        raise TypeError("validator programming failure")

    monkeypatch.setattr(ExecutionLedger, "finish", broken)
    config = Settings(_env_file=None, ai_execution_ledger_path=str(tmp_path / "calls.sqlite3"))
    with pytest.raises(TypeError, match="validator programming failure"):
        async with observation.interview_execution(config, "ws.answer", uuid4()):
            async with httpx.AsyncClient(
                transport=httpx.MockTransport(
                    lambda _incoming: httpx.Response(200, json=response())
                )
            ) as http:
                await client.call_model(
                    request(),
                    invalid,
                    api_key=SecretStr("fixture"),
                    base_url="https://provider.fixture/v1",
                    http_client=http,
                )


async def test_cancellation_while_optional_finish_runs_is_preserved(tmp_path, monkeypatch):
    entered, release = threading.Event(), threading.Event()

    def broken(self, record):
        entered.set()
        assert release.wait(timeout=5)
        raise sqlite3.OperationalError("disk full")

    monkeypatch.setattr(ExecutionLedger, "finish", broken)
    config = Settings(_env_file=None, ai_execution_ledger_path=str(tmp_path / "calls.sqlite3"))

    async def run():
        async with observation.interview_execution(config, "ws.answer", uuid4()):
            pass

    task = asyncio.create_task(run())
    assert await asyncio.to_thread(entered.wait, 5)
    task.cancel()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
