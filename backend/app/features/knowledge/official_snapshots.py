"""공식 공유 원문은 append-only이며 실제 사용은 면접 소유 source로 연결한다."""

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models.official_source import OfficialSourceSnapshot
from app.features.knowledge.official_catalog import (
    CatalogEntry,
    OfficialSourceError,
    SnapshotDraft,
    load_catalog,
    matching_entries,
    prepare_snapshot,
    source_matches_query,
)
from app.integrations.search.tavily import SearchError, WebSource


@dataclass(frozen=True)
class SharedSource:
    source: WebSource
    snapshot_id: UUID


@dataclass(frozen=True)
class SnapshotLookup:
    sources: tuple[SharedSource, ...] = ()
    limitations: tuple[str, ...] = ()


async def store_snapshots(
    sessions: async_sessionmaker[AsyncSession], drafts: tuple[SnapshotDraft, ...], *, actor: str
) -> tuple[UUID, ...]:
    if not actor.strip() or len(actor) > 128 or len(drafts) > 16:
        raise OfficialSourceError("collection_arguments_invalid")
    result = []
    catalog = load_catalog()
    async with sessions.begin() as db:
        for item in drafts:
            entry = item.entry
            checked = prepare_snapshot(
                entry,
                WebSource(
                    item.url,
                    item.title,
                    item.page_content,
                    "extracted_page",
                    item.retrieved_at,
                    item.page_content_hash,
                    limitations=item.limitations,
                ),
            )
            timestamp = datetime.fromisoformat(item.retrieved_at)
            if (
                checked != item
                or entry not in catalog
                or timestamp.tzinfo is None
                or timestamp > datetime.now(UTC) + timedelta(minutes=1)
            ):
                raise OfficialSourceError("snapshot_integrity_failed")
            values = dict(
                catalog_key=entry.catalog_key,
                catalog_hash=entry.definition_hash,
                domain_categories=list(entry.domain_categories),
                technology=entry.technology,
                technology_version=entry.version,
                language=entry.language,
                url=item.url,
                title=item.title,
                section_heading=entry.section_heading,
                content=item.content,
                content_hash=item.content_hash,
                page_content=item.page_content,
                page_content_hash=item.page_content_hash,
                start_line=item.start_line,
                end_line=item.end_line,
                retrieved_at=timestamp,
                provenance={
                    "collector": "tavily.extract",
                    "actor": actor.strip(),
                    "catalog": asdict(entry),
                    "catalog_url": entry.url,
                    "line_coordinates": "extracted_markdown",
                },
                limitations=list(item.limitations),
            )
            # 같은 수집 결과를 재전달해도 원문·시각·메타데이터는 덮어쓰지 않는다.
            identifier = await db.scalar(
                insert(OfficialSourceSnapshot)
                .values(**values)
                .on_conflict_do_nothing(constraint="uq_official_snapshot")
                .returning(OfficialSourceSnapshot.id)
            )
            if identifier is None:
                identifier = await db.scalar(
                    select(OfficialSourceSnapshot.id).where(
                        OfficialSourceSnapshot.catalog_key == entry.catalog_key,
                        OfficialSourceSnapshot.catalog_hash == entry.definition_hash,
                        OfficialSourceSnapshot.page_content_hash == item.page_content_hash,
                        OfficialSourceSnapshot.retrieved_at == values["retrieved_at"],
                    )
                )
            if identifier is None:
                raise OfficialSourceError("snapshot_store_failed")
            result.append(identifier)
    return tuple(result)


async def load_shared_sources(
    db: AsyncSession,
    query: str,
    category: str | None,
    *,
    max_age_seconds: int,
    now: datetime | None = None,
) -> SnapshotLookup:
    if max_age_seconds <= 0:
        raise OfficialSourceError("snapshot_age_invalid")
    now = now or datetime.now(UTC)
    found = []
    notes = []
    try:
        entries = matching_entries(query, category)[:3]
    except (OSError, ValueError, TypeError, SearchError):
        # 선택적인 공통 자료가 없어도 기존 검색을 유지하며 원문을 추측해 채우지 않는다.
        return SnapshotLookup((), ("official_catalog_unavailable",))
    for entry in entries:
        row = await db.scalar(
            select(OfficialSourceSnapshot)
            .where(
                OfficialSourceSnapshot.catalog_key == entry.catalog_key,
                OfficialSourceSnapshot.retrieved_at >= now - timedelta(seconds=max_age_seconds),
                OfficialSourceSnapshot.retrieved_at <= now,
            )
            .order_by(OfficialSourceSnapshot.retrieved_at.desc(), OfficialSourceSnapshot.id)
            .limit(1)
        )
        if row is None:
            notes.append(f"official_snapshot_unavailable:{entry.catalog_key}")
            continue
        page = WebSource(
            row.url,
            row.title,
            row.page_content,
            "extracted_page",
            row.retrieved_at.isoformat(),
            row.page_content_hash,
            limitations=tuple(row.limitations),
        )
        try:
            if row.catalog_hash != entry.definition_hash:
                # 이전 해시는 감사 메타데이터도 포함했다.
                # 원본 provenance를 검증한 뒤에만 재사용한다.
                legacy = row.provenance.get("catalog")
                if not isinstance(legacy, dict):
                    raise OfficialSourceError("snapshot_catalog_mismatch")
                previous = CatalogEntry(
                    **{
                        **legacy,
                        "domain_categories": tuple(legacy["domain_categories"]),
                        "query_terms": tuple(legacy["query_terms"]),
                        "limitations": tuple(legacy["limitations"]),
                    }
                )
                legacy_hash = hashlib.sha256(
                    json.dumps(asdict(previous), sort_keys=True).encode()
                ).hexdigest()
                if (
                    previous.definition_hash != entry.definition_hash
                    or legacy_hash != row.catalog_hash
                ):
                    raise OfficialSourceError("snapshot_catalog_mismatch")
            checked = prepare_snapshot(entry, page)
            if (
                checked.content != row.content
                or checked.content_hash != row.content_hash
                or (checked.start_line, checked.end_line) != (row.start_line, row.end_line)
                or row.technology != entry.technology
                or row.technology_version != entry.version
                or row.language != entry.language
                or row.domain_categories != list(entry.domain_categories)
            ):
                raise OfficialSourceError("snapshot_integrity_failed")
        except (OfficialSourceError, ValueError, KeyError, TypeError) as exc:
            reason = (
                str(exc) if isinstance(exc, OfficialSourceError) else "snapshot_integrity_failed"
            )
            notes.append(f"official_snapshot_rejected:{entry.catalog_key}:{reason}")
            continue
        source = WebSource(
            row.url,
            row.title,
            row.content,
            "extracted_page",
            row.retrieved_at.isoformat(),
            row.content_hash,
            limitations=tuple(row.limitations)
            + (
                f"official_snapshot:{row.id}",
                f"official_section:{row.section_heading}:markdown_lines={row.start_line}-{row.end_line}",
                f"official_version:{row.technology}:{row.technology_version}:{row.language}",
            ),
        )
        relevant, limitations = source_matches_query(
            query,
            source,
            technology=entry.technology,
            version=entry.version,
            language=entry.language,
        )
        if relevant:
            found.append(SharedSource(source, row.id))
        notes.extend(limitations)
    return SnapshotLookup(tuple(found), tuple(dict.fromkeys(notes)))
