import json

import httpx
import pytest
from pydantic import SecretStr

from app.integrations.search.tavily import (
    SearchBudget,
    SearchError,
    TavilyClient,
    TavilySettings,
)


def settings(**overrides):
    return TavilySettings(api_key=SecretStr("test-secret"), **overrides)


@pytest.mark.parametrize(
    "query",
    [
        "https://private.example",
        "me@example.invalid",
        "Redis\nprivate",
        "Bearer private-token",
        "phone 010-1234-5678",
    ],
)
async def test_unsafe_direct_query_never_spends_budget_or_calls_provider(query):
    def forbidden(request):
        pytest.fail("unsafe query reached provider")

    budget = SearchBudget(max_calls=2, max_credits=2)
    with pytest.raises(SearchError, match="unsafe_external_query"):
        await TavilyClient(settings(), httpx.MockTransport(forbidden)).search(
            query, domains=("docs.python.org",), budget=budget
        )
    assert budget.calls_used == budget.credits_used == 0


async def test_query_is_canonical_before_provider_request_and_restrict_is_kept():
    def respond(request):
        body = json.loads(request.content)
        assert body["query"] == "Python TaskGroup"
        assert body["include_domains_mode"] == "restrict"
        return httpx.Response(200, json={"results": [], "usage": {"credits": 0}})

    await TavilyClient(settings(), httpx.MockTransport(respond)).search(
        "  Python TaskGroup  ",
        domains=("docs.python.org",),
        budget=SearchBudget(max_calls=2, max_credits=2),
    )


@pytest.mark.asyncio
async def test_search_restricts_sources_and_preserves_snippet_provenance():
    def respond(request):
        body = json.loads(request.content)
        assert request.headers["authorization"] == "Bearer test-secret"
        assert body["include_domains_mode"] == "restrict"
        assert body["include_answer"] is False
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "url": "https://docs.python.org/3/",
                        "title": "Python",
                        "content": "원문 설명",
                    },
                    {"url": "https://unapproved.example/", "content": "범위 밖"},
                ],
                "usage": {"credits": 1},
            },
        )

    budget = SearchBudget(max_calls=2, max_credits=2)
    result = await TavilyClient(settings(), httpx.MockTransport(respond)).search(
        "문서 검색", domains=("docs.python.org",), budget=budget
    )
    assert len(result.sources) == 1
    source = result.sources[0]
    assert source.url == "https://docs.python.org/3/"
    assert source.content == "원문 설명"
    assert source.content_scope == "search_snippet"
    assert len(source.content_hash) == 64
    assert result.limitations == ("out_of_scope_result",)
    assert budget.calls_used == 1
    assert budget.credits_used == 1


@pytest.mark.asyncio
async def test_extract_preserves_per_url_failures_and_zero_usage():
    def respond(request):
        return httpx.Response(
            200,
            json={
                "results": [{"url": "https://docs.python.org/3/", "raw_content": "페이지 원문"}],
                "failed_results": [
                    {"url": "https://docs.python.org/missing", "error": "provider text"}
                ],
                "usage": {"credits": 0},
            },
        )

    budget = SearchBudget(max_calls=2, max_credits=2)
    result = await TavilyClient(settings(), httpx.MockTransport(respond)).extract(
        ("https://docs.python.org/3/", "https://docs.python.org/missing"),
        domains=("docs.python.org",),
        budget=budget,
    )
    assert result.sources[0].content_scope == "extracted_page"
    assert result.failures[0].url == "https://docs.python.org/missing"
    assert result.failures[0].reason == "extraction_failed"
    assert "provider text" not in str(result.failures)
    assert result.credits == 0
    assert budget.credits_used == 0


@pytest.mark.parametrize(
    "url",
    [
        "http://docs.python.org/",
        "https://user:secret@docs.python.org/",
        "https://127.0.0.1/",
        "https://localhost/",
        "https://docs.python.org.evil.example/",
    ],
)
@pytest.mark.asyncio
async def test_invalid_extract_url_fails_before_network(url):
    calls = []
    client = TavilyClient(settings(), httpx.MockTransport(lambda r: calls.append(r)))
    with pytest.raises(SearchError, match="invalid_source"):
        await client.extract((url,), domains=("docs.python.org",), budget=SearchBudget(2, 2))
    assert calls == []


@pytest.mark.parametrize(
    "status,reason",
    [
        (401, "unauthorized"),
        (429, "rate_limited"),
        (432, "quota_exhausted"),
        (433, "quota_exhausted"),
    ],
)
@pytest.mark.asyncio
async def test_provider_failure_does_not_expose_credentials(status, reason):
    client = TavilyClient(
        settings(), httpx.MockTransport(lambda r: httpx.Response(status, text="test-secret"))
    )
    with pytest.raises(SearchError) as got:
        await client.search("query", domains=("docs.python.org",), budget=SearchBudget(2, 2))
    assert got.value.reason == reason
    assert "test-secret" not in str(got.value)


@pytest.mark.asyncio
async def test_call_budget_prevents_unbounded_searches():
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(200, json={"results": [], "usage": {"credits": 1}})

    client = TavilyClient(settings(), httpx.MockTransport(respond))
    budget = SearchBudget(1, 1)
    await client.search("first", domains=("docs.python.org",), budget=budget)
    with pytest.raises(SearchError, match="budget_exhausted"):
        await client.search("second", domains=("docs.python.org",), budget=budget)
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_response_and_content_limits_are_explicit():
    client = TavilyClient(
        settings(max_content_chars=3),
        httpx.MockTransport(
            lambda r: httpx.Response(
                200, json={"results": [{"url": "https://docs.python.org/", "content": "abcdef"}]}
            )
        ),
    )
    result = await client.search("query", domains=("docs.python.org",), budget=SearchBudget(1, 1))
    assert result.sources[0].content == "abc"
    assert result.sources[0].limitations == ("content_truncated",)
    client = TavilyClient(
        settings(max_response_bytes=32),
        httpx.MockTransport(lambda r: httpx.Response(200, content=b"x" * 33)),
    )
    with pytest.raises(SearchError, match="response_too_large"):
        await client.search("query", domains=("docs.python.org",), budget=SearchBudget(1, 1))


@pytest.mark.parametrize("value", [float("inf"), -1, True])
def test_budget_limits_must_be_finite_integers(value):
    with pytest.raises(ValueError):
        SearchBudget(value, 1)


@pytest.mark.asyncio
async def test_invalid_unicode_query_is_rejected_without_network_or_raw_error():
    calls = []
    client = TavilyClient(settings(), httpx.MockTransport(lambda r: calls.append(r)))
    with pytest.raises(SearchError, match="invalid_query"):
        await client.search(
            "private\ud800", domains=("docs.python.org",), budget=SearchBudget(1, 1)
        )
    assert calls == []
