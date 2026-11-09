"""공통 원문은 사용자와 독립 저장하고 실제 면접에는 소유 source로 연결한다."""

import hashlib
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from devon_ai import contracts as c
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from app.core.config import Settings
from app.db.models import InterviewExternalSource, InterviewSession, User
from app.db.models.official_source import OfficialSourceSnapshot
from app.features.knowledge.official_catalog import load_catalog, prepare_snapshot
from app.integrations.search.tavily import WebSource
from tests.features.interview.factories import make_interview, make_repo, make_run, make_user


def draft():
    content = (
        "# Coroutines\n## Task Groups\nPython asyncio TaskGroup cancels tasks on "
        "failure and handles CancelledError.\n## Sleeping\nOther details."
    )
    entry = next(item for item in load_catalog() if item.catalog_key == "python-3.12-task-groups")
    return prepare_snapshot(
        entry,
        WebSource(
            "https://docs.python.org/3.12/library/asyncio-task.html",
            "Python 3.12 tasks",
            content,
            "extracted_page",
            datetime.now(UTC).isoformat(),
            hashlib.sha256(content.encode()).hexdigest(),
        ),
    )


async def test_shared_store_has_no_fake_owner_and_preserves_immutable_original(app):
    from app.features.knowledge.official_snapshots import store_snapshots

    sessions = app.state.session_factory
    original = draft()
    first = await store_snapshots(sessions, (original,), actor="test-operator")
    second = await store_snapshots(sessions, (original,), actor="test-operator")
    assert first == second
    async with sessions() as db:
        assert await db.scalar(select(func.count()).select_from(User)) == 0
        assert await db.scalar(select(func.count()).select_from(InterviewSession)) == 0
        row = await db.get(OfficialSourceSnapshot, first[0])
        assert row.content == original.content and row.page_content == original.page_content
        assert row.content_hash == original.content_hash
        assert row.provenance["line_coordinates"] == "extracted_markdown"
        assert row.provenance["catalog_url"].endswith("#task-groups")
    async with sessions.begin() as db:
        with pytest.raises(DBAPIError, match="immutable"):
            async with db.begin_nested():
                await db.execute(text("UPDATE official_source_snapshots SET content = 'changed'"))
        with pytest.raises(DBAPIError, match="immutable"):
            async with db.begin_nested():
                await db.execute(text("DELETE FROM official_source_snapshots"))


async def test_shared_snapshot_is_used_without_provider_credentials_and_keeps_interview_ownership(
    app,
):
    from app.features.interview.external_knowledge import retrieve_external_knowledge
    from app.features.knowledge.official_snapshots import store_snapshots

    sessions = app.state.session_factory
    snapshot_ids = await store_snapshots(sessions, (draft(),), actor="test-operator")
    async with sessions.begin() as db:
        owner = await make_user(db)
        other = await make_user(db)
        run = await make_run(db, owner)
        repo = await make_repo(db, run)
        interview = await make_interview(db, run, [repo])
    settings = Settings(_env_file=None)
    args = dict(
        interview_id=interview.id,
        queries=(
            c.ExternalQueryRequest("Python 3.12 asyncio TaskGroup cancellation", "기술 개념 확인"),
        ),
        settings=settings,
    )
    result = await retrieve_external_knowledge(sessions, user_id=owner.id, **args)
    assert result.status == "found" and len(result.sources) == 1
    assert "TaskGroup" in result.sources[0].content
    second = await retrieve_external_knowledge(sessions, user_id=owner.id, **args)
    assert second.sources[0].source_id == result.sources[0].source_id
    async with sessions() as db:
        stored = list(await db.scalars(select(InterviewExternalSource)))
        assert len(stored) == 1 and stored[0].official_snapshot_id == snapshot_ids[0]
        assert stored[0].user_id == owner.id and stored[0].interview_session_id == interview.id
        row = await db.get(InterviewSession, interview.id)
        assert row.context_state.get("external_search_usage", {"calls": 0})["calls"] == 0
    denied = await retrieve_external_knowledge(sessions, user_id=other.id, **args)
    assert denied.status == "tool_error" and denied.sources == ()


async def test_version_mismatch_falls_back_without_adopting_unrelated_official_results(
    app,
):
    from app.features.interview.external_knowledge import retrieve_external_knowledge
    from app.features.knowledge.official_snapshots import store_snapshots
    from app.integrations.search.tavily import TavilyClient

    sessions = app.state.session_factory
    await store_snapshots(sessions, (draft(),), actor="test-operator")
    async with sessions.begin() as db:
        owner = await make_user(db)
        run = await make_run(db, owner)
        repo = await make_repo(db, run)
        interview = await make_interview(db, run, [repo])
    calls = []

    def handler(request):
        calls.append(request.url.path)
        url = "https://docs.python.org/fr/3.7/library/asyncio-exceptions.html"
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "url": url,
                        "content": "TaskGroup cancellation",
                        "raw_content": "TaskGroup cancellation",
                    }
                ],
                "usage": {"credits": 1},
            },
        )

    settings = Settings(_env_file=None, tavily_api_key="test-key")
    provider = TavilyClient(settings.require_tavily(), transport=httpx.MockTransport(handler))
    result = await retrieve_external_knowledge(
        sessions,
        user_id=owner.id,
        interview_id=interview.id,
        queries=(
            c.ExternalQueryRequest("Python 3.13 asyncio TaskGroup cancellation", "기술 개념 확인"),
        ),
        settings=settings,
        client=provider,
    )
    assert result.status != "found" and result.sources == ()
    assert calls == ["/search", "/extract"]
    assert "source_version_mismatch" in result.limitations
    async with sessions() as db:
        assert await db.scalar(select(func.count()).select_from(InterviewExternalSource)) == 0


async def test_shared_snapshot_cache_time_does_not_claim_a_new_provider_validation(app):
    from app.features.interview.external_knowledge import retrieve_external_knowledge
    from app.features.knowledge.official_snapshots import store_snapshots

    sessions = app.state.session_factory
    original = replace(
        draft(), retrieved_at=(datetime.now(UTC) - timedelta(minutes=50)).isoformat()
    )
    await store_snapshots(sessions, (original,), actor="test-operator")
    async with sessions.begin() as db:
        owner = await make_user(db)
        run = await make_run(db, owner)
        repo = await make_repo(db, run)
        interview = await make_interview(db, run, [repo])
    result = await retrieve_external_knowledge(
        sessions,
        user_id=owner.id,
        interview_id=interview.id,
        queries=(
            c.ExternalQueryRequest("Python 3.12 asyncio TaskGroup cancellation", "개념 확인"),
        ),
        settings=Settings(_env_file=None, external_sources_cache_seconds=3600),
    )
    assert result.status == "found"
    async with sessions() as db:
        row = await db.get(InterviewSession, interview.id)
        timestamps = [
            datetime.fromisoformat(item["validated_at"])
            for item in row.context_state["external_query_cache"].values()
        ]
        assert timestamps == [datetime.fromisoformat(original.retrieved_at)]


async def test_snapshot_storage_rejects_a_modified_selected_passage_before_writing(app):
    from app.features.knowledge.official_catalog import OfficialSourceError
    from app.features.knowledge.official_snapshots import store_snapshots

    item = replace(draft(), content="Fabricated selected passage")
    with pytest.raises(OfficialSourceError, match="snapshot_integrity_failed"):
        await store_snapshots(app.state.session_factory, (item,), actor="test-operator")
    async with app.state.session_factory() as db:
        assert await db.scalar(select(func.count()).select_from(OfficialSourceSnapshot)) == 0


async def test_partial_owned_alias_with_foreign_id_is_not_a_complete_cache_hit(app):
    from app.features.interview.external_knowledge import _cache_key, retrieve_external_knowledge
    from app.features.knowledge.official_catalog import scope_domains
    from app.integrations.search.tavily import TavilyClient

    sessions = app.state.session_factory
    content = "Redis session architecture details"
    now = datetime.now(UTC)
    async with sessions.begin() as db:
        owner = await make_user(db)
        run = await make_run(db, owner)
        repo = await make_repo(db, run)
        interview = await make_interview(db, run, [repo])
        other = await make_user(db)
        other_run = await make_run(db, other)
        other_repo = await make_repo(db, other_run)
        other_interview = await make_interview(db, other_run, [other_repo])
        rows = []
        for user, session in [(owner, interview), (other, other_interview)]:
            row = InterviewExternalSource(
                user_id=user.id,
                interview_session_id=session.id,
                query_text="Redis session architecture",
                url="https://elice.io/reference",
                content=content,
                content_hash=hashlib.sha256(content.encode()).hexdigest(),
                content_scope="extracted_page",
                retrieved_at=now,
                limitations=[],
            )
            db.add(row)
            rows.append(row)
        await db.flush()
        interview.context_state = {
            "external_query_cache": {
                _cache_key("Redis session architecture", scope_domains("etc")): {
                    "source_ids": [str(row.id) for row in rows],
                    "validated_at": now.isoformat(),
                }
            }
        }
    calls = []

    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "url": "https://elice.io/reference",
                        "content": content,
                        "raw_content": content,
                    }
                ],
                "usage": {"credits": 1},
            },
        )

    settings = Settings(_env_file=None, tavily_api_key="test-key")
    provider = TavilyClient(settings.require_tavily(), transport=httpx.MockTransport(handler))
    result = await retrieve_external_knowledge(
        sessions,
        user_id=owner.id,
        interview_id=interview.id,
        queries=(c.ExternalQueryRequest("Redis session architecture", "개념 확인"),),
        settings=settings,
        client=provider,
    )
    assert result.status == "found" and calls == ["/search", "/extract"]
    assert [item.source_id for item in result.sources] == [str(rows[0].id)]
