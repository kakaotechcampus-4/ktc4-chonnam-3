"""시작 시 자동 수집하지 않고 명시 요청한 공식 URL만 유한 예산으로 수집한다."""

from dataclasses import asdict
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.features.knowledge.official_catalog import (
    OfficialSourceError,
    load_catalog,
    prepare_snapshot,
    scope_domains,
)
from app.features.knowledge.official_snapshots import store_snapshots
from app.integrations.search.tavily import (
    SearchBudget,
    SearchError,
    TavilyClient,
    checked_source_url,
)


async def collect_official_catalog(
    sessions: async_sessionmaker[AsyncSession] | None,
    *,
    catalog_keys: tuple[str, ...],
    provider: TavilyClient | None,
    budget: SearchBudget,
    actor: str,
    apply: bool = False,
) -> dict[str, object]:
    catalog = {item.catalog_key: item for item in load_catalog()}
    if (
        not catalog_keys
        or len(catalog_keys) > 16
        or len(set(catalog_keys)) != len(catalog_keys)
        or not set(catalog_keys) <= set(catalog)
        or not actor.strip()
        or len(actor) > 128
    ):
        raise OfficialSourceError("collection_arguments_invalid")
    entries = tuple(catalog[key] for key in catalog_keys)
    failures = {
        item.catalog_key: f"catalog_access_{item.availability}"
        for item in entries
        if item.availability != "public_verified"
    }
    snapshots = []
    if apply:
        if provider is None or sessions is None:
            raise OfficialSourceError("collection_not_configured")
        allowed = tuple(
            dict.fromkeys(
                domain
                for item in entries
                for category in item.domain_categories
                for domain in scope_domains(category)
            )
        )
        eligible = [item for item in entries if item.catalog_key not in failures]
        for start in range(0, len(eligible), 5):
            batch = eligible[start : start + 5]
            urls = tuple(dict.fromkeys(item.url for item in batch))
            try:
                result = await provider.extract(urls, domains=allowed, budget=budget)
            except SearchError as exc:
                failures.update({item.catalog_key: f"extraction:{exc.reason}" for item in batch})
                continue
            sources = {source.url: source for source in result.sources}
            for entry in batch:
                source = sources.get(checked_source_url(entry.url, allowed))
                if source is None:
                    failures[entry.catalog_key] = "extraction_failed"
                    continue
                try:
                    snapshots.append(prepare_snapshot(entry, source))
                except OfficialSourceError as exc:
                    failures[entry.catalog_key] = str(exc)
    identifiers: list[UUID] = []
    # 항목별 트랜잭션으로 이미 수집한 다른 원문과 외부 사용량의 감사 기록을 보존한다.
    if sessions is not None:
        for snapshot in snapshots:
            try:
                identifiers.extend(await store_snapshots(sessions, (snapshot,), actor=actor))
            except OfficialSourceError as exc:
                failures[snapshot.entry.catalog_key] = str(exc)
            except SQLAlchemyError:
                failures[snapshot.entry.catalog_key] = "snapshot_store_failed"
    return {
        "format_version": 1,
        "catalog_version": "official-catalog.v1",
        "catalog_verification": "url_access_only_extraction_is_verified_per_run",
        "mode": "applied" if apply else "dry_run",
        "actor": actor.strip(),
        "sources": [asdict(item) for item in entries],
        "snapshot_ids": [str(identifier) for identifier in identifiers],
        "failures": failures,
        "calls_used": budget.calls_used,
        "credits_used": budget.credits_used,
        "limits": {"max_calls": budget.max_calls, "max_credits": budget.max_credits},
    }
