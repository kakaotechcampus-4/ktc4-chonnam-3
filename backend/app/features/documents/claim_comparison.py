"""선택 문서와 고정 SHA 코드의 대조를 한 배치로 실행·저장·재사용한다."""

import asyncio
import hashlib
import json
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID, uuid4

import httpx
from devon_ai import contracts as c
from devon_ai.llm_tasks.claim_code import (
    MAX_CLAIMS,
    MAX_EVIDENCES,
    ClaimComparisonResult,
    ClaimForComparison,
    unverified,
    unverified_reason,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import LLMSettings, Settings
from app.db.models import (
    DocumentClaim,
    DocumentClaimComparison,
    Evidence,
    InterviewSession,
    LLMCallRecord,
    SessionRepository,
    UserDocument,
)
from app.features.documents.selection import selected_documents
from app.features.interview.prepare_lease import owns_preparation
from app.llm_tasks.conflict import compare_document_claims
from app.llm_tasks.prompt_loader import (
    PromptConfigurationError,
    PromptNotFoundError,
    load_active_prompt,
)

CODE_INPUT_BYTES = 65536


def _expires(state: dict[str, Any]) -> datetime | None:
    raw = state.get("document_claim_comparison_expires_at")
    try:
        value = datetime.fromisoformat(raw) if isinstance(raw, str) else None
    except ValueError:
        return None
    return value if value is not None and value.tzinfo is not None else None


def _hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


@dataclass(frozen=True)
class _Input:
    claims: tuple[ClaimForComparison, ...]
    evidences: tuple[c.Evidence, ...]
    code_sources: tuple[dict[str, Any], ...]
    limitations: tuple[str, ...]

    def fingerprint(self, prompt: c.PromptSpec | None) -> str:
        return _hash(
            {
                "claims": [asdict(item) for item in self.claims],
                "evidences": [asdict(item) for item in self.evidences],
                "limitations": self.limitations,
                "budget": {
                    "claims": MAX_CLAIMS,
                    "evidences": MAX_EVIDENCES,
                    "code_bytes": CODE_INPUT_BYTES,
                },
                "prompt": asdict(prompt) if prompt else None,
            }
        )


async def _owned(
    db: AsyncSession,
    interview_id: UUID,
    job_id: UUID,
) -> InterviewSession | None:
    row = await db.scalar(
        select(InterviewSession).where(InterviewSession.id == interview_id).with_for_update()
    )
    return row if row is not None and owns_preparation(row, job_id=job_id) else None


async def _input(db: AsyncSession, interview: InterviewSession) -> _Input:
    documents = await selected_documents(db, interview)
    if not documents:
        return _Input((), (), (), ())
    # 문서 추출의 전역 교체와 같은 잠금 순서를 사용하고 외부 호출 전 트랜잭션을 끝낸다.
    rows = await db.scalars(
        select(UserDocument)
        .where(UserDocument.id.in_([d.id for d in documents]))
        .order_by(UserDocument.id)
        .with_for_update()
    )
    documents = tuple(rows)
    claims: list[ClaimForComparison] = []
    for document in documents:
        snapshot = document.source_snapshot or {}
        text = snapshot.get("text")
        if type(text) is not str or hashlib.sha256(text.encode()).hexdigest() != snapshot.get(
            "text_hash"
        ):
            continue
        active = set(document.claims_active_ids or ())
        for claim in await db.scalars(
            select(DocumentClaim)
            .where(DocumentClaim.document_id == document.id)
            .order_by(DocumentClaim.created_at, DocumentClaim.id)
        ):
            if (
                str(claim.id) not in active
                or claim.source_version != snapshot["text_hash"]
                or not claim.source_text
                or claim.source_text not in text
            ):
                continue
            assert claim.source_version is not None
            claims.append(
                ClaimForComparison(
                    str(claim.id),
                    claim.claim_type or "unknown",
                    claim.claim_text,
                    claim.source_text,
                    claim.source_version,
                    json.dumps(
                        {**(claim.source_location or {}), "document_id": str(document.id)},
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                )
            )
    sources = await db.scalars(
        select(Evidence)
        .join(
            SessionRepository,
            (SessionRepository.interview_session_id == Evidence.interview_session_id)
            & (SessionRepository.repository_id == Evidence.repository_id)
            & (SessionRepository.snapshot_head_sha == Evidence.git_ref),
        )
        .where(Evidence.interview_session_id == interview.id, Evidence.source_type == "file")
        .order_by(Evidence.repository_id, Evidence.path, Evidence.start_line, Evidence.id)
    )
    evidences: list[c.Evidence] = []
    references: list[dict[str, Any]] = []
    remaining, omitted = CODE_INPUT_BYTES, 0
    for item in sources:
        size = len(item.snippet.encode())
        if (
            not item.path
            or not item.snippet.strip()
            or size > remaining
            or len(evidences) >= MAX_EVIDENCES
        ):
            omitted += 1
            continue
        evidences.append(
            c.Evidence(
                str(item.id),
                str(item.repository_id),
                item.git_ref,
                item.source_type,
                item.path,
                item.metadata_key,
                item.snippet,
                item.tool_name,
                item.summary,
                item.start_line,
                item.end_line,
            )
        )
        references.append(
            {
                "evidence_id": str(item.id),
                "repository_id": str(item.repository_id),
                "git_ref": item.git_ref,
                "path": item.path,
                "start_line": item.start_line,
                "end_line": item.end_line,
                "content_hash": hashlib.sha256(item.snippet.encode()).hexdigest(),
            }
        )
        remaining -= size
    limitations = ("provided_code_snippets_only",) + (
        (f"comparison_code_budget_excluded:{omitted}",) if omitted else ()
    )
    return _Input(tuple(claims), tuple(evidences), tuple(references), limitations)


def _state(
    row: InterviewSession,
    status: str,
    count: int,
    error: str | None = None,
    ids: tuple[str, ...] = (),
) -> None:
    row.context_state = {
        **(row.context_state or {}),
        "document_claim_comparison_status": status,
        "document_claim_comparison_count": count,
        "document_claim_comparison_error": error,
        "document_claim_comparison_active_ids": list(ids),
    }
