"""수동 공식 URL 수집은 명시 예산의 extract만 사용하며 startup에서는 실행하지 않는다."""

import json

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import Settings
from app.db.models.official_source import OfficialSourceSnapshot
from app.integrations.search.tavily import SearchBudget, TavilyClient


@pytest.mark.parametrize(
    "query", ["database=unapproved_database", "host=unapproved_host", "ssl=require"]
)
def test_cli_rejects_connection_query_options_before_any_io(query):
    from app.features.knowledge.official_catalog import OfficialSourceError
    from scripts.collect_official_sources import validate_collection_target
    from scripts.configure_ai_knowledge import KnowledgeTarget

    url = "postgresql+asyncpg://devon:devon@127.0.0.1:15441/approved_test?" + query
    settings = Settings(_env_file=None, database_url=url)
    with pytest.raises(OfficialSourceError, match="database_query_options_not_permitted"):
        validate_collection_target(
            settings, KnowledgeTarget("test", "127.0.0.1", 15441, "approved_test")
        )


async def test_actual_connected_database_is_verified_without_any_write(test_database_url):
    from app.features.knowledge.official_catalog import OfficialSourceError
    from scripts.collect_official_sources import verify_collection_database
    from scripts.configure_ai_knowledge import KnowledgeTarget

    url = make_url(test_database_url)
    assert url.database
    engine = create_async_engine(test_database_url)
    try:
        target = KnowledgeTarget("test", url.host, url.port, url.database)
        await verify_collection_database(engine, target)
        with pytest.raises(OfficialSourceError, match="connected_database_mismatch"):
            await verify_collection_database(
                engine, KnowledgeTarget("test", url.host, url.port, "different_database_test")
            )
    finally:
        await engine.dispose()


async def test_collection_dry_run_needs_no_database_or_provider():
    from app.features.knowledge.official_collection import collect_official_catalog

    result = await collect_official_catalog(
        None,
        catalog_keys=("python-3.12-task-groups",),
        provider=None,
        budget=SearchBudget(0, 0),
        actor="test-operator",
        apply=False,
    )
    assert result["mode"] == "dry_run" and result["calls_used"] == 0
    assert result["snapshot_ids"] == []


async def test_collection_extracts_exact_catalog_url_and_stores_only_verified_section(app):
    from app.features.knowledge.official_collection import collect_official_catalog

    calls = []

    def handler(request):
        calls.append(request.url.path)
        assert request.url.path == "/extract"
        body = json.loads(request.content)
        assert body["urls"] == ["https://docs.python.org/3.12/library/asyncio-task.html"]
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "url": body["urls"][0],
                        "raw_content": (
                            "# Coroutines\n## Task Groups\nPython asyncio TaskGroup "
                            "details.\n## Sleeping\nOther."
                        ),
                    }
                ],
                "usage": {"credits": 1},
            },
        )

    settings = Settings(_env_file=None, tavily_api_key="test-key")
    provider = TavilyClient(settings.require_tavily(), transport=httpx.MockTransport(handler))
    result = await collect_official_catalog(
        app.state.session_factory,
        catalog_keys=("python-3.12-task-groups",),
        provider=provider,
        budget=SearchBudget(1, 1),
        actor="test-operator",
        apply=True,
    )
    assert result["calls_used"] == 1 and result["credits_used"] == 1
    assert len(result["snapshot_ids"]) == 1 and result["failures"] == {}
    assert calls == ["/extract"]
    async with app.state.session_factory() as db:
        row = await db.scalar(select(OfficialSourceSnapshot))
        assert row.section_heading == "Task Groups"
        assert row.content == "## Task Groups\nPython asyncio TaskGroup details."


async def test_unverified_javascript_portal_is_reported_without_any_http_or_fake_snapshot(app):
    from app.features.knowledge.official_collection import collect_official_catalog

    def forbidden(request):
        raise AssertionError("unsupported catalog source reached provider")

    settings = Settings(_env_file=None, tavily_api_key="test-key")
    provider = TavilyClient(settings.require_tavily(), transport=httpx.MockTransport(forbidden))
    result = await collect_official_catalog(
        app.state.session_factory,
        catalog_keys=("tourapi-portal",),
        provider=provider,
        budget=SearchBudget(1, 1),
        actor="test-operator",
        apply=True,
    )
    assert result["failures"] == {"tourapi-portal": "catalog_access_javascript_required"}
    assert result["snapshot_ids"] == [] and result["calls_used"] == 0
    async with app.state.session_factory() as db:
        assert await db.scalar(select(func.count()).select_from(OfficialSourceSnapshot)) == 0


def test_cli_catalog_listing_does_not_read_private_env_or_initialize_database(
    tmp_path, monkeypatch
):
    from scripts import collect_official_sources as cli

    def forbidden(*args, **kwargs):
        raise AssertionError("catalog listing read runtime settings")

    monkeypatch.setattr(cli, "Settings", forbidden)
    output = tmp_path / "catalog.json"
    assert cli.main(["--list", "--output", str(output)]) == 0
    saved = json.loads(output.read_text("utf-8"))
    assert saved["mode"] == "catalog_only"
    assert any(item["availability"] == "javascript_required" for item in saved["sources"])
