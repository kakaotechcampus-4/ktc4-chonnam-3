"""Director 진입점·단계 관측. 원문을 기록하거나 외부 서버에 전송하지 않는다."""

import asyncio
import logging
import sqlite3
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager, nullcontext
from functools import wraps
from pathlib import Path
from uuid import UUID, uuid4

from app.core.config import Settings
from app.integrations.execution_ledger import (
    ExecutionLedger,
    Observation,
    execution_scope,
    observe_call,
)

_logger = logging.getLogger(__name__)


@asynccontextmanager
async def interview_execution(
    settings: Settings, operation: str, interview_id: UUID, *, turn: int | None = None
) -> AsyncIterator[Observation | None]:
    metadata: dict[str, str | int | bool | None] = {"interview_id": str(interview_id)}
    if turn is not None:
        metadata["turn"] = turn
    path = settings.ai_execution_ledger_path
    # 장부는 선택 설정이며 Langfuse 전송은 실행 뒤 별도 명령에서 수행한다.
    ledger = None
    if path is not None:
        try:
            ledger = await asyncio.to_thread(ExecutionLedger, Path(path))
        except (OSError, sqlite3.OperationalError) as error:
            _logger.warning(
                "ai_execution_ledger_io_failed",
                extra={"phase": "initialize", "exception_type": type(error).__name__},
            )
    scope = (
        execution_scope(
            ledger,
            run_id=str(uuid4()),
            entrypoint=operation,
            metadata=metadata,
            ignore_io_errors=True,
        )
        if ledger is not None
        else nullcontext()
    )
    with scope:
        async with observe_call(operation, kind="stage", metadata=metadata) as observed:
            yield observed


def observed_stage[**P, T](
    operation: str,
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    def decorate(function: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        @wraps(function)
        async def execute(*args: P.args, **kwargs: P.kwargs) -> T:
            async with observe_call(operation, kind="stage"):
                return await function(*args, **kwargs)

        return execute

    return decorate
