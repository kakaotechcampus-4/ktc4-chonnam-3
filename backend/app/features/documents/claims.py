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


async def _prepare_document_once(
    sessions: async_sessionmaker[AsyncSession],
    interview_id: UUID,
    document_id: UUID,
    job_id: UUID,
    settings: Settings,
    http_client: httpx.AsyncClient | None,
) -> bool:
    run_id = uuid4()
    async with sessions.begin() as db:
        row = await _interview(db, interview_id)
        if row is None or not owns_preparation(row, job_id=job_id):
            return False
        if document_id not in {item.id for item in await selected_documents(db, row)}:
            return False
        document = await db.scalar(
            select(UserDocument)
            .where(UserDocument.id == document_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        assert document is not None
        snapshot = document.source_snapshot
        if not snapshot and document.extracted_text:
            text = document.extracted_text
            # 과거 축약문을 원본 파일 전체를 복원한 것으로 표시하지 않는다.
            snapshot = {
                "text": text,
                "text_hash": hashlib.sha256(text.encode()).hexdigest(),
                "source_hash": None,
                "blocks": [],
                "limitations": ["legacy_preview_only"],
            }
            document.source_snapshot = snapshot
        if not snapshot or not snapshot.get("text"):
            document.claims_status = "not_available"
            _state(row, document_id, "not_available", "document_source_unavailable")
            return False
        text = snapshot["text"]
        if type(text) is not str or hashlib.sha256(text.encode()).hexdigest() != snapshot.get(
            "text_hash"
        ):
            document.claims_status, document.claims_error_code = "failed", "document_source_invalid"
            _state(row, document_id, "failed", "document_source_invalid")
            return False
        try:
            # 본문·모델이 불변인 prompt version도 캐시 키에 포함한다.
            prompt = await load_active_prompt(db, "doc_claims")
            llm = settings.require_llm()
        except (PromptNotFoundError, PromptConfigurationError, ValueError):
            _state(row, document_id, "failed", "doc_claims_not_configured")
            return False
        source_version = snapshot["text_hash"]
        if (
            document.claims_status == "succeeded"
            and document.claims_source_version == source_version
            and document.claims_prompt_version == prompt.version
        ):
            _state(row, document_id, "succeeded")
            return False
        if document.claims_status == "running" and (
            document.claims_lease_expires_at is None
            or document.claims_lease_expires_at > datetime.now(UTC)
        ):
            # 예약 수명은 작성자가 확정한다. 만료를 모르는 구형 예약도 짧은 대기자의
            # 예산으로 탈취하지 않고 이번 면접의 유한 대기 뒤 미확인 상태로 남긴다.
            _state(row, document_id, "pending")
            return True
        document.claims_status, document.claims_error_code = "running", None
        document.claims_run_id = run_id
        document.claims_lease_expires_at = datetime.now(UTC) + timedelta(
            seconds=3 * llm.call_limits("doc_claims").timeout_seconds
        )
        _state(row, document_id, "pending")

    attempts: list[c.AttemptMetadata] = []

    async def store(result: ClaimExtraction, *, cancelled: bool = False) -> None:
        async with sessions.begin() as db:
            row = await _interview(db, interview_id)
            if row is None:
                return
            document = await db.scalar(
                select(UserDocument)
                .where(UserDocument.id == document_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            record = LLMCallRecord(
                id=run_id,
                interview_session_id=interview_id,
                task_name="doc_claims",
                attempts=[asdict(item) for item in result.attempts],
                failure=asdict(result.failure) if result.failure else None,
            )
            db.add(record)
            valid = (
                owns_preparation(row, job_id=job_id)
                and document is not None
                and document.claims_run_id == run_id
                and document_id in {item.id for item in await selected_documents(db, row)}
                and document.source_snapshot
                and document.source_snapshot.get("text_hash") == source_version
            )
            try:
                active = await load_active_prompt(db, "doc_claims") if valid else None
            except (PromptNotFoundError, PromptConfigurationError):
                active = None
            if cancelled or not valid or active != prompt:
                record.discard_reason = (
                    "preparation_cancelled"
                    if cancelled
                    else "selected_document_or_preparation_changed"
                )
                owns_reservation = document is not None and document.claims_run_id == run_id
                if document is not None and owns_reservation:
                    document.claims_status, document.claims_run_id = "pending", None
                    document.claims_lease_expires_at = None
                if owns_reservation and owns_preparation(row, job_id=job_id):
                    _state(
                        row,
                        document_id,
                        "pending",
                        "document_claims_cancelled" if cancelled else "document_claims_stale",
                    )
                return
            assert document is not None
            document.claims_run_id = None
            document.claims_lease_expires_at = None
            if result.failure:
                document.claims_status, document.claims_error_code = (
                    "failed",
                    result.failure.error_code,
                )
                _state(row, document_id, "failed", result.failure.error_code)
                return
            try:
                # 위치를 모두 확인한 뒤에만 새 Claim을 저장해 부분 성공을 만들지 않는다.
                locations = [
                    claim_location(snapshot, item.paragraph_no, item.source_line)
                    for item in result.claims
                ]
            except ValueError:
                record.failure = asdict(
                    c.CallFailure(
                        "semantic", "document_source_invalid", "Claim source location rejected."
                    )
                )
                document.claims_status, document.claims_error_code = (
                    "failed",
                    "document_source_invalid",
                )
                _state(row, document_id, "failed", "document_source_invalid")
                return
            active_claims = []
            for item, location in zip(result.claims, locations, strict=True):
                # 재분류·태그·원문 위치가 달라지면 과거 대조가 참조하는 행을 바꾸지 않는다.
                existing = await db.scalar(
                    select(DocumentClaim)
                    .where(
                        DocumentClaim.document_id == document_id,
                        DocumentClaim.source_version == source_version,
                        DocumentClaim.paragraph_no == item.paragraph_no,
                        DocumentClaim.claim_text == item.claim_text,
                        DocumentClaim.claim_type == item.claim_type,
                        DocumentClaim.tech_tags == list(item.tech_tags),
                        DocumentClaim.source_text == item.source_line,
                        DocumentClaim.source_location == location,
                    )
                    .order_by(DocumentClaim.created_at, DocumentClaim.id)
                    .limit(1)
                )
                if existing is None:
                    existing = DocumentClaim(
                        document_id=document_id,
                        claim_text=item.claim_text,
                        claim_type=item.claim_type,
                        tech_tags=list(item.tech_tags),
                        paragraph_no=item.paragraph_no,
                        source_text=item.source_line,
                        source_location=location,
                        source_version=source_version,
                    )
                    db.add(existing)
                active_claims.append(existing)
            await db.flush()
            document.claims_active_ids = [str(item.id) for item in active_claims]
            document.claims_status, document.claims_error_code = "succeeded", None
            document.claims_source_version, document.claims_prompt_version = (
                source_version,
                prompt.version,
            )
            _state(row, document_id, "succeeded")

    try:
        result = await analyze_document_claims(
            text, prompt=prompt, settings=llm, http_client=http_client, attempt_sink=attempts
        )
    except asyncio.CancelledError:
        await asyncio.shield(
            store(
                ClaimExtraction(
                    (),
                    c.CallFailure(
                        "provider", "document_claims_cancelled", "Document analysis cancelled."
                    ),
                    tuple(attempts),
                ),
                cancelled=True,
            )
        )
        raise
    await store(result)
    return False
