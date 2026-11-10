"""공식 자료의 정책 식별·언어·유한 원문·부분 실패 경계를 검증한다."""

import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.features.knowledge import official_catalog as catalog
from app.integrations.search.tavily import WebSource


def entry():
    return next(
        item for item in catalog.load_catalog() if item.catalog_key == "python-3.12-task-groups"
    )


def source(body, *, url="https://docs.python.org/3.12/library/asyncio-task.html"):
    return WebSource(
        url,
        "Python asyncio",
        body,
        "extracted_page",
        datetime.now(UTC).isoformat(),
        hashlib.sha256(body.encode()).hexdigest(),
    )


def test_catalog_audit_metadata_does_not_invalidate_content_but_access_policy_does():
    original = entry()
    changed = replace(original, verified_at="2026-11-09", limitations=("new audit note",))
    assert changed.definition_hash == original.definition_hash
    for changed in (
        replace(original, availability="login_required"),
        replace(original, version="3.13"),
        replace(original, query_terms=("other",)),
    ):
        assert changed.definition_hash != original.definition_hash


def test_english_query_does_not_require_english_document():
    entries = catalog.matching_entries("openbanking balance", "finance")
    assert [item.catalog_key for item in entries] == ["kftc-openbanking-balance"]
    assert catalog._language("openbanking balance") is None
    assert catalog._language("openbanking balance english") == "en"


def test_known_korean_concept_matches_english_source_without_loosening_api_checks():
    candidate = source("TaskGroup cancels tasks on failure.")
    assert catalog.source_matches_query("파이썬 3.12 TaskGroup 취소", candidate)[0]
    assert not catalog.source_matches_query(
        "파이썬 3.12 TaskGroup 취소", source("Python navigation")
    )[0]
    assert not catalog.source_matches_query("파이썬 3.12 ExceptionGroup 취소", candidate)[0]


def test_numeric_alias_does_not_match_a_longer_number():
    assert catalog._has_alias("http 429", "429")
    assert not catalog._has_alias("http 4290", "429")
    assert catalog._has_alias("java17", "java")
    assert not catalog._has_alias("javascript", "java")


def test_concept_alias_cannot_erase_an_explicit_lowercase_identifier():
    candidate = source("Python cancels tasks.")
    assert not catalog.source_matches_query("Python cancelled_error", candidate)[0]
    assert not catalog.source_matches_query("Python 취소취약점", candidate)[0]


def test_large_page_keeps_complete_requested_section_and_original_line_coordinates():
    prefix = "intro\n" * 9000
    page = prefix + "## Task Groups\nTaskGroup cancellation.\n## Sleeping\nOther."
    draft = catalog.prepare_snapshot(entry(), source(page))
    assert len(page) > 24000
    assert draft.start_line == 9001
    assert draft.content == "## Task Groups\nTaskGroup cancellation."
    assert draft.page_content == page
    assert draft.page_content_hash == hashlib.sha256(page.encode()).hexdigest()


def test_section_and_page_budgets_are_independent_and_finite():
    with pytest.raises(catalog.OfficialSourceError, match="section_content_budget"):
        catalog.prepare_snapshot(entry(), source("## Task Groups\n" + "x" * 24000))
    with pytest.raises(catalog.OfficialSourceError, match="source_content_budget"):
        catalog.prepare_snapshot(entry(), source("x" * (catalog.MAX_PAGE_CONTENT_CHARS + 1)))


@pytest.mark.parametrize("raw", [{}, [], {"version": "official-catalog.v1", "sources": [{}]}])
def test_missing_catalog_fields_are_a_controlled_optional_source_error(monkeypatch, raw):
    monkeypatch.setattr(catalog.Path, "read_text", lambda *a, **kw: json.dumps(raw))
    with pytest.raises(catalog.OfficialSourceError, match="catalog_invalid"):
        catalog.load_catalog()


async def test_optional_invalid_catalog_keeps_search_fallback_available(monkeypatch):
    from app.features.knowledge.official_snapshots import load_shared_sources

    monkeypatch.setattr(catalog.Path, "read_text", lambda *a, **kw: "{}")
    result = await load_shared_sources(None, "Python TaskGroup", "etc", max_age_seconds=3600)
    assert result.sources == ()
    assert result.limitations == ("official_catalog_unavailable",)


def test_cli_never_overwrites_existing_audit(tmp_path, capsys):
    from scripts.collect_official_sources import main

    path = tmp_path / "existing.json"
    path.write_text("original", encoding="utf-8")
    assert main(["--list", "--output", str(path)]) == 1
    assert path.read_text(encoding="utf-8") == "original"
    assert "output_already_exists" in capsys.readouterr().err


async def test_collection_keeps_other_items_and_credit_audit_after_one_store_failure(monkeypatch):
    from app.core.config import Settings
    from app.features.knowledge import official_collection as collection
    from app.integrations.search.tavily import SearchBudget, TavilyClient

    first = entry()
    second = replace(first, catalog_key="python-second-section", section_heading="Sleeping")
    monkeypatch.setattr(collection, "load_catalog", lambda: (first, second))
    identifier = uuid4()
    stored = []

    async def store(sessions, drafts, *, actor):
        stored.append(drafts[0].entry.catalog_key)
        if len(stored) == 1:
            raise catalog.OfficialSourceError("snapshot_integrity_failed")
        return (identifier,)

    def handler(request):
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "url": "https://docs.python.org/3.12/library/asyncio-task.html",
                        "raw_content": (
                            "## Task Groups\nTaskGroup.\n## Sleeping\nSleep.\n## Other\nOther."
                        ),
                    }
                ],
                "usage": {"credits": 1},
            },
        )

    monkeypatch.setattr(collection, "store_snapshots", store)
    provider = TavilyClient(
        Settings(_env_file=None, tavily_api_key="fixture").require_tavily(),
        transport=httpx.MockTransport(handler),
    )
    result = await collection.collect_official_catalog(
        object(),
        catalog_keys=(first.catalog_key, second.catalog_key),
        provider=provider,
        budget=SearchBudget(1, 1),
        actor="fixture",
        apply=True,
    )
    assert stored == [first.catalog_key, second.catalog_key]
    assert result["snapshot_ids"] == [str(identifier)]
    assert result["failures"] == {first.catalog_key: "snapshot_integrity_failed"}
    assert result["calls_used"] == result["credits_used"] == 1


async def test_snapshot_truncate_is_rejected_with_the_runtime_guard_enabled(app):
    async with app.state.session_factory.begin() as db:
        with pytest.raises(DBAPIError, match="immutable"):
            async with db.begin_nested():
                await db.execute(
                    text("TRUNCATE official_source_snapshots, interview_external_sources")
                )
