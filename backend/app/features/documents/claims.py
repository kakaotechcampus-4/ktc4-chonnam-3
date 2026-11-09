"""선택 문서의 주장·원문 위치를 보존하고 오래된 준비 작업의 덮어쓰기를 막는다."""

import asyncio
import hashlib
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID, uuid4

import httpx
from devon_ai import contracts as c
from devon_ai.llm_tasks.doc_claims import ClaimExtraction
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.db.models import DocumentClaim, InterviewSession, LLMCallRecord, UserDocument
from app.features.documents.selection import selected_documents
from app.features.documents.source_snapshot import claim_location
from app.features.interview.prepare_lease import owns_preparation
from app.llm_tasks.doc_claims import analyze_document_claims
from app.llm_tasks.prompt_loader import (
    PromptConfigurationError,
    PromptNotFoundError,
    load_active_prompt,
)

CLAIM_POLL_SECONDS = 0.1


def _state(row: InterviewSession, document_id: UUID, status: str, error: str | None = None) -> None:
    state = dict(row.context_state or {})
    raw = state.get("document_claims_results", {})
    if not isinstance(raw, dict) or any(not isinstance(item, dict) for item in raw.values()):
        raise c.ContractError("schema", "document claim results")
    results = dict(cast(dict[str, dict[str, str | None]], raw))
    results[str(document_id)] = {"status": status, "error_code": error}
    statuses = {item["status"] for item in results.values()}
    overall = next(
        (value for value in ("failed", "pending", "not_available") if value in statuses),
        "succeeded",
    )
    state.update(
        document_claims_results=results,
        document_claims_status=overall,
        document_claims_error_code=next(
            (item["error_code"] for item in results.values() if item["error_code"]), None
        ),
    )
    row.context_state = state


async def _interview(db: AsyncSession, interview_id: UUID) -> InterviewSession | None:
    # heartbeat와 같은 행을 먼저 잠가 context_state 전체의 변경을 직렬화한다.
    return cast(
        InterviewSession | None,
        await db.scalar(
            select(InterviewSession).where(InterviewSession.id == interview_id).with_for_update()
        ),
    )


async def prepare_selected_document_claims(
    sessions: async_sessionmaker[AsyncSession],
    interview_id: UUID,
    settings: Settings,
    http_client: httpx.AsyncClient | None = None,
    *,
    job_id: UUID,
) -> None:
    async with sessions.begin() as db:
        row = await _interview(db, interview_id)
        if row is None or not owns_preparation(row, job_id=job_id):
            return
        ids = tuple(document.id for document in await selected_documents(db, row))
    for document_id in ids:
        await _prepare_document(sessions, interview_id, document_id, job_id, settings, http_client)


async def _prepare_document(
    sessions: async_sessionmaker[AsyncSession],
    interview_id: UUID,
    document_id: UUID,
    job_id: UUID,
    settings: Settings,
    http_client: httpx.AsyncClient | None,
) -> None:
    try:
        timeout = 3 * settings.require_llm().call_limits("doc_claims").timeout_seconds
    except ValueError:
        await _prepare_document_once(
            sessions, interview_id, document_id, job_id, settings, http_client
        )
        return
    try:
        # 다른 면접의 결과를 DB 잠금 밖에서 기다리며 동일 문서의 모델 호출을 중복하지 않는다.
        # 대기·실행·저장을 합쳐 기존 문서 한 건의 3T 준비 예산을 넘지 않는다.
        async with asyncio.timeout(timeout):
            while True:
                if not await _prepare_document_once(
                    sessions, interview_id, document_id, job_id, settings, http_client
                ):
                    break
                await asyncio.sleep(CLAIM_POLL_SECONDS)
    except TimeoutError:
        async with sessions.begin() as db:
            row = await _interview(db, interview_id)
            if row is not None and owns_preparation(row, job_id=job_id):
                _state(row, document_id, "not_available", "document_claims_wait_timeout")
