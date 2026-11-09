"""분석 run·후보 페이지 실패 로그: 예상 밖 예외에만 안전한 진단 위치를 남긴다.

예외 원문(SQL 문·인자·문서 본문)은 Console·JSON 어느 최종 출력에도 나오면 안 된다.
"""

import json
import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
import structlog
from sqlalchemy.exc import ProgrammingError, StatementError
from structlog.testing import capture_logs

from app.core.errors import AppError, Reason
from app.core.logging import configure_logging
from app.features.analysis.pipeline import run as run_module
from app.features.analysis.pipeline.run_support import RunFailure
from app.integrations.jd.base import PostingUnreachableError
from app.llm_tasks.jd_extract import JdExtractionError

SECRET = "시험용-민감-문서-본문"


def _statement_error() -> StatementError:
    return StatementError(
        "(builtins.ValueError) bad", "INSERT INTO t VALUES (:v)", {"v": SECRET}, ValueError(SECRET)
    )


def _program_error() -> ProgrammingError:
    # SQLAlchemy 예외는 자체 `.code`("f405")가 있어 `.code` 로 분류하면 예상 실패로 오인된다.
    return ProgrammingError(f"SELECT {SECRET}", {"v": SECRET}, Exception(SECRET))


# (예외 생성, 예상 업무 실패인지)
CASES = [
    pytest.param(lambda: KeyError(SECRET), False, id="key_error"),
    pytest.param(_statement_error, False, id="sql_statement_error"),
    pytest.param(_program_error, False, id="sql_programming_error_has_code_attr"),
    pytest.param(lambda: RunFailure("jd_fetch_failed"), True, id="run_failure"),
    pytest.param(lambda: AppError(Reason.GITHUB_TOKEN_INVALID), True, id="app_error"),
    pytest.param(lambda: PostingUnreachableError(SECRET), True, id="posting_fetch_error"),
    pytest.param(lambda: JdExtractionError("jd_extraction_failed", SECRET), True, id="jd_error"),
]


def _patch_run(monkeypatch, error):
    run = SimpleNamespace(created_at=datetime.now(UTC), user_id=uuid4(), document_id=None)
    finished: list[tuple] = []

    async def claim_run(ctx, run_id):
        return run

    async def account_for_run(ctx, user_id):
        raise error

    async def finish_run(ctx, run_id, status, code):
        finished.append((status, code))

    monkeypatch.setattr(run_module, "claim_run", claim_run)
    monkeypatch.setattr(run_module, "account_for_run", account_for_run)
    monkeypatch.setattr(run_module, "finish_run", finish_run)
    return finished


def _patch_page(monkeypatch, error):
    run = SimpleNamespace(status="succeeded", created_at=datetime.now(UTC))
    row = SimpleNamespace(status="pending")
    finished: list[str | None] = []

    class Db:
        async def get(self, *_):
            return run

        async def scalar(self, *_):
            return row

        def expunge(self, _):
            pass

    class Factory:
        @asynccontextmanager
        async def begin(self):
            yield Db()

    async def collect(ctx, run, page):
        raise error

    async def finish_page(ctx, run_id, page, code):
        finished.append(code)

    monkeypatch.setattr(run_module, "collect", collect)
    monkeypatch.setattr(run_module, "finish_page", finish_page)
    ctx = {"session_factory": Factory(), "settings": SimpleNamespace(analysis_run_ttl_seconds=3600)}
    return ctx, finished


def _run_ctx():
    return {"settings": SimpleNamespace(analysis_run_ttl_seconds=3600)}


async def _fail_run(monkeypatch, error):
    finished = _patch_run(monkeypatch, error)
    await run_module.run_analysis(_run_ctx(), uuid4())
    return finished


async def _fail_page(monkeypatch, error):
    ctx, finished = _patch_page(monkeypatch, error)
    await run_module.run_candidate_page(ctx, uuid4(), 2)
    return finished


@pytest.mark.asyncio
@pytest.mark.parametrize(("make_error", "expected"), CASES)
@pytest.mark.parametrize(
    ("runner", "event"),
    [(_fail_run, "analysis_run_failed"), (_fail_page, "analysis_page_failed")],
)
async def test_only_unexpected_failures_log_a_safe_error_chain(
    monkeypatch, make_error, expected, runner, event
):
    with capture_logs() as logs:
        finished = await runner(monkeypatch, make_error())

    [entry] = [log for log in logs if log["event"] == event]
    assert "exc_info" not in entry  # 예외 원문·체인을 직접 넘기지 않는다
    assert ("error_chain" not in entry) is expected
    assert finished  # 기존처럼 실패 종료까지 간다
    assert SECRET not in json.dumps(entry, ensure_ascii=False, default=str)
    if not expected:
        [outer, *_] = entry["error_chain"]
        assert outer["type"].endswith(type(make_error()).__qualname__)
        assert outer["frames"]  # 파일:함수:줄번호


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("make_error", "code"),
    [
        (lambda: PostingUnreachableError(SECRET), "jd_fetch_failed"),
        (lambda: JdExtractionError("jd_extraction_failed"), "jd_extraction_failed"),
        (lambda: AppError(Reason.GITHUB_TOKEN_INVALID), "token_invalid"),
    ],
)
async def test_failure_code_and_finish_state_are_unchanged(monkeypatch, make_error, code):
    assert await _fail_run(monkeypatch, make_error()) == [("failed", code)]
    assert await _fail_page(monkeypatch, make_error()) == [code]


@pytest.fixture
def reset_structlog():
    yield
    structlog.reset_defaults()


@pytest.mark.asyncio
@pytest.mark.parametrize("json_logs", [False, True], ids=["console", "json"])
@pytest.mark.parametrize("runner", [_fail_run, _fail_page])
async def test_final_output_has_error_location_but_no_exception_text(
    monkeypatch, caplog, reset_structlog, json_logs, runner
):
    configure_logging("INFO", json_logs=json_logs)
    with caplog.at_level(logging.INFO):
        await runner(monkeypatch, _statement_error())

    output = "\n".join(caplog.messages)
    assert "StatementError" in output  # 예외 타입
    assert "test_run_failure_logging.py" in output  # 호출 위치(파일)
    assert SECRET not in output
    assert "INSERT INTO" not in output  # SQL 문
    assert "Traceback" not in output
    if json_logs:
        [line] = [m for m in caplog.messages if "error_chain" in m]
        assert json.loads(line)["error_chain"][0]["frames"]
