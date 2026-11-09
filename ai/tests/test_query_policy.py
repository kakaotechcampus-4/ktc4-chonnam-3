"""과거 자료 복원과 새 외부 실행 검증을 구분한다."""

from dataclasses import asdict

import pytest

from devon_ai import contracts as c


@pytest.mark.parametrize(
    "query",
    [
        "https://private.example",
        "redis://private.example",
        "file:///private/path",
        "me@example.invalid",
        "Redis\nprivate",
        "Redis\u2028private",
        "Bearer fixture-token",
        "phone 010-1234-5678",
        "id 900101-1234567",
        "```code```",
    ],
)
def test_historical_query_restores_but_cannot_be_executed(query):
    raw = {"query": query, "purpose": "historical fixture"}
    restored = c.decode_strict(c.ExternalQueryRequest, raw)
    assert asdict(restored) == raw
    with pytest.raises(c.ContractError, match="unsafe_external_query"):
        restored.validate_for_execution()


def test_execution_canonical_query_does_not_mutate_preserved_input():
    request = c.ExternalQueryRequest("  Python TaskGroup  ", "공식 개념 확인")
    assert request.validate_for_execution() == "Python TaskGroup"
    assert request.query == "  Python TaskGroup  "


def test_phone_shaped_order_number_is_conservatively_blocked_without_claiming_all_pii_detection():
    with pytest.raises(c.ContractError, match="unsafe_external_query"):
        c.ExternalQueryRequest("order 01012345678", "fixture").validate_for_execution()


@pytest.mark.parametrize("query", ["HTTP 404", "Python 3.12.10 asyncio", "Redis 7.2 TTL 3600"])
def test_normal_technical_queries_remain_allowed(query):
    assert c.ExternalQueryRequest(query, "fixture").validate_for_execution() == query
