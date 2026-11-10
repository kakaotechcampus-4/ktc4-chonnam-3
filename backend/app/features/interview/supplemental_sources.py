"""면접에 연결한 문서 주장과 외부 원문을 코드 Evidence와 구분해 읽는다."""

import json
from uuid import UUID

from devon_ai import contracts as c
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    DocumentClaim,
    InterviewExternalSource,
    InterviewSession,
)
from app.features.documents.selection import selected_documents


async def load_external_searches(
    db: AsyncSession, interview_id: UUID
) -> tuple[c.ExternalSearchStatus, ...]:
    interview = await db.get(InterviewSession, interview_id)
    if interview is None:
        return ()
    raw = (interview.context_state or {}).get("external_searches", [])
    if not isinstance(raw, list):
        raise c.ContractError("schema", "external search state")
    return tuple(c.decode_strict(c.ExternalSearchStatus, item) for item in raw)


async def load_supplemental_sources(
    db: AsyncSession,
    interview_id: UUID,
    *,
    max_total_bytes: int | None = 16384,
    source_refs: frozenset[c.BasisRef] | None = None,
) -> tuple[c.SupplementalSource, ...]:
    interview = await db.get(InterviewSession, interview_id)
    if interview is None:
        return ()
    documents = await selected_documents(db, interview)
    result: list[c.SupplementalSource] = []
    for document in documents:
        if not document.source_snapshot:
            continue
        snapshot = document.source_snapshot
        claims = await db.scalars(
            select(DocumentClaim)
            .where(
                DocumentClaim.document_id == document.id,
                DocumentClaim.source_text.is_not(None),
            )
            .order_by(DocumentClaim.created_at, DocumentClaim.id)
        )
        for claim in claims:
            historical = (
                document.claims_active_ids is not None
                and str(claim.id) not in document.claims_active_ids
            ) or claim.source_version != snapshot.get("text_hash")
            if max_total_bytes is not None and source_refs is None and historical:
                continue
            version = claim.source_version
            if version is None:
                continue
            location = json.dumps(claim.source_location or {}, ensure_ascii=False, sort_keys=True)
            result.append(
                c.SupplementalSource(
                    source_id=str(claim.id),
                    kind="document_claim",
                    content=f"문서의 주장: {claim.claim_text}\n문서 원문: {claim.source_text}",
                    location=f"document:{document.id}:{location}",
                    version=version,
                    limitations=tuple(snapshot.get("limitations", []))
                    + ("document_claim_unverified",)
                    + (("historical_document_claim",) if historical else ()),
                    title=document.filename,
                )
            )
        metadata = snapshot.get("metadata", {})
        source_hash = snapshot.get("source_hash")
        if isinstance(metadata, dict) and isinstance(source_hash, str) and len(source_hash) == 64:
            for item in metadata.get("visual_interpretations", []):
                description = item.get("description")
                if not isinstance(description, str) or not description.strip():
                    continue
                result.append(
                    c.SupplementalSource(
                        source_id=f"{document.id}:visual:{item.get('page')}:{item.get('element')}",
                        kind="document_visual",
                        content=description,
                        location=f"document:{document.id}:page={item.get('page')}:element={item.get('element')}",
                        version=source_hash,
                        title=document.filename,
                        limitations=(
                            "generated_visual_interpretation_not_transcription",
                            "not_personal_contribution_evidence",
                        ),
                    )
                )
    external = await db.scalars(
        select(InterviewExternalSource)
        .where(
            InterviewExternalSource.interview_session_id == interview.id,
            InterviewExternalSource.user_id == interview.user_id,
        )
        .order_by(InterviewExternalSource.retrieved_at.desc(), InterviewExternalSource.id)
    )
    for item in external:
        # 오래된 인용도 재현해야 하므로 Context에서는 TTL로 지우지 않는다. 검색 캐시에만 적용한다.
        result.append(
            c.SupplementalSource(
                source_id=str(item.id),
                kind="external_source",
                content=item.content,
                location=item.url,
                version=item.content_hash,
                limitations=tuple(item.limitations)
                + ("external_reference_not_personal_contribution_evidence",),
                title=item.title,
                retrieved_at=item.retrieved_at.isoformat(),
            )
        )
    from app.features.documents.claim_comparison import load_claim_comparison_sources

    result.extend(
        await load_claim_comparison_sources(
            db, interview, include_historical=max_total_bytes is None or source_refs is not None
        )
    )
    if source_refs is not None:
        # 리포트는 실제 질문한 과거 참조를 먼저 고르고 그 안에서 동일한 본문 예산을 적용한다.
        result = [
            source for source in result if c.BasisRef(source.kind, source.source_id) in source_refs
        ]
    if max_total_bytes is None:
        # 과거 질문의 참조 복원 전용이다. 이 전체 목록을 모델 Context로 전달하지 않는다.
        return tuple(result)
    if max_total_bytes <= 0:
        raise ValueError("Source context budget must be positive")
    from collections import deque
    from dataclasses import replace

    # 문서별·외부 자료별로 번갈아 읽어 한 문서가 전체 Context 예산을 독점하지 않게 한다.
    buckets: dict[str, deque[c.SupplementalSource]] = {}
    for source in result:
        bucket = source.location.split(":", 2)[1] if source.kind != "external_source" else "web"
        buckets.setdefault(bucket, deque()).append(source)
    ordered = []
    while any(buckets.values()):
        for queue in buckets.values():
            if queue:
                ordered.append(queue.popleft())
    bounded: list[c.SupplementalSource] = []
    remaining = max_total_bytes
    for source in ordered:
        if remaining <= 0:
            break
        limit = min(4096, remaining)
        size = len(source.content.encode("utf-8"))
        if size > limit:
            content = source.content.encode("utf-8")[:limit].decode("utf-8", errors="ignore")
            if content.strip():
                bounded.append(
                    replace(
                        source,
                        content=content,
                        limitations=source.limitations + ("context_excerpt",),
                    )
                )
                remaining -= len(content.encode("utf-8"))
            continue
        bounded.append(source)
        remaining -= size
    return tuple(bounded)
