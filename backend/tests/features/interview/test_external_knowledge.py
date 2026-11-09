"""검색부터 실제 외부 원문 저장·재사용까지 검사한다."""

import httpx
import pytest
from devon_ai import contracts as c
from sqlalchemy import func, select

from app.core.config import Settings
from app.db.models import InterviewExternalSource
from app.integrations.search.tavily import TavilyClient
from tests.features.interview.factories import make_interview, make_repo, make_run, make_user


async def test_verified_query_searches_extracts_stores_and_reuses_cache(app):
    from app.features.interview.external_knowledge import retrieve_external_knowledge

    async with app.state.session_factory.begin() as db:
        owner = await make_user(db)
        run = await make_run(db, owner)
        repo = await make_repo(db, run)
        interview = await make_interview(db, run, [repo], status="in_progress")
    calls = []

    def handler(request):
        calls.append(request.url.path)
        if request.url.path == "/search":
            import json

            assert json.loads(request.content)["query"] == "Redis session architecture"
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "url": "https://elice.io/reference",
                            "title": "Reference",
                            "content": "snippet",
                        }
                    ],
                    "usage": {"credits": 1},
                },
            )
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "url": "https://elice.io/reference",
                        "raw_content": "Actual official document text",
                    }
                ],
                "failed_results": [],
                "usage": {"credits": 0},
            },
        )

    settings = Settings(_env_file=None, tavily_api_key="test-key")
    provider = TavilyClient(settings.require_tavily(), transport=httpx.MockTransport(handler))
    args = dict(
        user_id=owner.id,
        interview_id=interview.id,
        queries=(c.ExternalQueryRequest("  Redis session architecture  ", "기술 개념 확인"),),
        settings=settings,
        client=provider,
    )
    first = await retrieve_external_knowledge(app.state.session_factory, **args)
    assert first.status == "found"
    assert first.sources[0].content == "Actual official document text"
    assert first.sources[0].location == "https://elice.io/reference"
    args["queries"] = (c.ExternalQueryRequest("Redis session architecture", "기술 개념 확인"),)
    second = await retrieve_external_knowledge(app.state.session_factory, **args)
    assert second.sources[0].source_id == first.sources[0].source_id
    assert calls == ["/search", "/extract"]
    async with app.state.session_factory() as db:
        rows = list(await db.scalars(select(InterviewExternalSource)))
        assert len(rows) == 1 and rows[0].query_text == "Redis session architecture"


async def test_one_unsafe_query_blocks_the_entire_batch_before_http_and_source_storage(app):
    from app.features.interview.external_knowledge import retrieve_external_knowledge

    async with app.state.session_factory.begin() as db:
        owner = await make_user(db)
        run = await make_run(db, owner)
        repo = await make_repo(db, run)
        interview = await make_interview(db, run, [repo], status="in_progress")

    def forbidden(request):
        pytest.fail("mixed unsafe batch reached provider")

    settings = Settings(_env_file=None, tavily_api_key="fixture")
    provider = TavilyClient(settings.require_tavily(), transport=httpx.MockTransport(forbidden))
    result = await retrieve_external_knowledge(
        app.state.session_factory,
        user_id=owner.id,
        interview_id=interview.id,
        queries=(
            c.ExternalQueryRequest("Redis TTL", "fixture"),
            c.ExternalQueryRequest("Redis\nprivate", "fixture"),
        ),
        settings=settings,
        client=provider,
    )
    assert result.error_code == "unsafe_external_query" and result.sources == ()
    async with app.state.session_factory() as db:
        assert await db.scalar(select(func.count()).select_from(InterviewExternalSource)) == 0


@pytest.mark.parametrize(
    "secret_query",
    [
        "Bearer secret-token-value",
        "phone 010-1234-5678",
        "identifier 900101-1234567",
    ],
)
async def test_external_provider_is_not_called_for_other_user_or_secret_query(app, secret_query):
    from app.features.interview.external_knowledge import retrieve_external_knowledge

    async with app.state.session_factory.begin() as db:
        owner = await make_user(db)
        outsider = await make_user(db)
        run = await make_run(db, owner)
        repo = await make_repo(db, run)
        interview = await make_interview(db, run, [repo], status="in_progress")

    def forbidden(request):
        raise AssertionError("Unauthorized query reached external provider")

    settings = Settings(_env_file=None, tavily_api_key="test-key")
    provider = TavilyClient(settings.require_tavily(), transport=httpx.MockTransport(forbidden))
    result = await retrieve_external_knowledge(
        app.state.session_factory,
        user_id=outsider.id,
        interview_id=interview.id,
        queries=(c.ExternalQueryRequest("architecture", "개념 확인"),),
        settings=settings,
        client=provider,
    )
    assert result.status == "tool_error"
    result = await retrieve_external_knowledge(
        app.state.session_factory,
        user_id=owner.id,
        interview_id=interview.id,
        queries=(c.ExternalQueryRequest(secret_query, "조회"),),
        settings=settings,
        client=provider,
    )
    assert result.status == "tool_error"
    assert result.error_code == "unsafe_external_query"


@pytest.mark.parametrize(
    "query", ["phone 010-1234-5678", "phone +82 10-1234-5678", "identifier 900101-1234567"]
)
def test_clearly_formatted_phone_or_resident_number_is_not_an_external_query(query):
    from app.features.interview.external_knowledge import _PRIVATE

    assert _PRIVATE.search(query) is not None


@pytest.mark.parametrize("reason", ["expired_same_content", "query_alias"])
async def test_revalidation_or_query_alias_reuses_immutable_source_without_repeated_billing(
    app, reason
):
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import select

    from app.db.models import InterviewExternalSource, InterviewSession
    from app.features.interview.external_knowledge import retrieve_external_knowledge

    async with app.state.session_factory.begin() as db:
        owner = await make_user(db)
        run = await make_run(db, owner)
        repo = await make_repo(db, run)
        interview = await make_interview(db, run, [repo], status="in_progress")
    calls = []

    def handler(req):
        calls.append(req.url.path)
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "url": "https://elice.io/reference",
                        "title": "Reference",
                        "content": "snippet",
                    }
                ]
                if req.url.path == "/search"
                else [
                    {
                        "url": "https://elice.io/reference",
                        "raw_content": "Same immutable original passage",
                    }
                ],
                "usage": {"credits": 1 if req.url.path == "/search" else 0},
                "failed_results": [],
            },
        )

    settings = Settings(
        _env_file=None, tavily_api_key="test-key", external_sources_cache_seconds=60
    )
    provider = TavilyClient(settings.require_tavily(), transport=httpx.MockTransport(handler))
    args = dict(user_id=owner.id, interview_id=interview.id, settings=settings, client=provider)
    original_query = c.ExternalQueryRequest("Redis architecture", "개념 확인")
    first = await retrieve_external_knowledge(
        app.state.session_factory, queries=(original_query,), **args
    )
    async with app.state.session_factory.begin() as db:
        row = await db.scalar(select(InterviewExternalSource))
        if reason == "expired_same_content":
            row.retrieved_at = datetime.now(UTC) - timedelta(minutes=2)
            session = await db.get(InterviewSession, interview.id)
            state = dict(session.context_state or {})
            aliases = dict(state.get("external_query_cache", {}))
            for key, entry in aliases.items():
                aliases[key] = {**entry, "validated_at": row.retrieved_at.isoformat()}
            session.context_state = {**state, "external_query_cache": aliases}
        original_time, original_hash = row.retrieved_at, row.content_hash
    query = (
        original_query
        if reason == "expired_same_content"
        else c.ExternalQueryRequest("Redis reliability", "다른 개념 확인")
    )
    second = await retrieve_external_knowledge(app.state.session_factory, queries=(query,), **args)
    third = await retrieve_external_knowledge(app.state.session_factory, queries=(query,), **args)
    assert first.sources[0].source_id == second.sources[0].source_id == third.sources[0].source_id
    assert calls == ["/search", "/extract", "/search", "/extract"]
    async with app.state.session_factory() as db:
        rows = list(await db.scalars(select(InterviewExternalSource)))
        assert len(rows) == 1
        assert rows[0].retrieved_at == original_time and rows[0].content_hash == original_hash
        assert rows[0].query_text == original_query.query
        session = await db.get(InterviewSession, interview.id)
        assert session.context_state["external_search_usage"]["calls"] == 4
