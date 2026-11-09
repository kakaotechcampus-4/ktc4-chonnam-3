"""Tavily 검색·본문 추출. 공급자 원문 오류와 비밀키는 외부로 전달하지 않는다."""

from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import json
import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

import httpx
from devon_ai.query_policy import ExternalQueryError, canonical_external_query
from pydantic import SecretStr


class SearchError(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class TavilySettings:
    api_key: SecretStr
    timeout_seconds: float = 20
    max_response_bytes: int = 1048576
    max_content_chars: int = 24000
    max_results: int = 5

    def __post_init__(self) -> None:
        if not self.api_key.get_secret_value().strip():
            raise ValueError("Tavily API key is required")
        if not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0:
            raise ValueError("Tavily timeout must be positive")
        if any(
            type(x) is not int or x <= 0
            for x in (self.max_response_bytes, self.max_content_chars, self.max_results)
        ):
            raise ValueError("Tavily limits must be positive integers")
        if self.max_results > 20:
            raise ValueError("Tavily result limit exceeds provider maximum")


@dataclass
class SearchBudget:
    max_calls: int
    max_credits: int
    calls_used: int = 0
    credits_used: int = 0

    def __post_init__(self) -> None:
        if any(
            type(value) is not int or value < 0
            for value in (self.max_calls, self.max_credits, self.calls_used, self.credits_used)
        ):
            raise ValueError("Search budgets must be finite nonnegative integers")
        if self.calls_used > self.max_calls or self.credits_used > self.max_credits:
            raise ValueError("Search budget is already exceeded")

    def reserve(self) -> None:
        # 기본 검색과 최대 5개 URL 기본 추출은 요청당 1크레딧을 보수적으로 예약한다.
        if self.calls_used >= self.max_calls or self.credits_used >= self.max_credits:
            raise SearchError("budget_exhausted")
        self.calls_used += 1
        self.credits_used += 1

    def settle(self, credits: int | None) -> None:
        # 사용량 미제공은 무료로 해석하지 않는다. 명시적인 0은 공급자 반환값 그대로 기록한다.
        if credits is not None:
            self.credits_used += credits - 1
        if self.credits_used > self.max_credits:
            raise SearchError("budget_exhausted")


@dataclass(frozen=True)
class WebSource:
    url: str
    title: str | None
    content: str
    content_scope: Literal["search_snippet", "extracted_page"]
    retrieved_at: str
    content_hash: str
    published_at: str | None = None
    limitations: tuple[str, ...] = ()


@dataclass(frozen=True)
class SearchResult:
    sources: tuple[WebSource, ...]
    credits: int | None
    limitations: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExtractFailure:
    url: str
    reason: str


@dataclass(frozen=True)
class ExtractResult:
    sources: tuple[WebSource, ...]
    failures: tuple[ExtractFailure, ...]
    credits: int | None
    limitations: tuple[str, ...] = ()


def _domains(domains: tuple[str, ...]) -> tuple[str, ...]:
    if not domains or len(domains) > 100:
        raise SearchError("invalid_source")
    normalized = []
    for domain in domains:
        try:
            host = domain.encode("idna").decode("ascii").lower()
        except (UnicodeError, AttributeError):
            raise SearchError("invalid_source") from None
        if not re.fullmatch(r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}", host):
            raise SearchError("invalid_source")
        if host.endswith((".local", ".internal", ".localhost", ".test", ".invalid")):
            raise SearchError("invalid_source")
        normalized.append(host)
    return tuple(dict.fromkeys(normalized))


def checked_source_url(url: object, domains: tuple[str, ...]) -> str:
    """허용한 공개 HTTPS 도메인만 공급자에 전달한다. 사용자 입력 URL로 내부망을 읽지 않는다."""
    if (
        not isinstance(url, str)
        or len(url) > 8192
        or any(c.isspace() or ord(c) < 32 for c in url)
        or "\\" in url
    ):
        raise SearchError("invalid_source")
    try:
        value = urlsplit(url)
        host = (value.hostname or "").encode("idna").decode("ascii").lower()
        port = value.port
        if (
            value.scheme != "https"
            or not host
            or value.username is not None
            or value.password is not None
            or port not in (None, 443)
        ):
            raise SearchError("invalid_source")
        try:
            ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            raise SearchError("invalid_source")
    except (ValueError, UnicodeError):
        raise SearchError("invalid_source") from None
    allowed = _domains(domains)
    if not any(host == domain or host.endswith("." + domain) for domain in allowed):
        raise SearchError("invalid_source")
    return urlunsplit(("https", host, value.path or "/", value.query, ""))


class TavilyClient:
    def __init__(
        self, settings: TavilySettings, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self.settings, self.transport = settings, transport

    async def search(
        self,
        query: str,
        *,
        domains: tuple[str, ...],
        budget: SearchBudget,
        max_results: int | None = None,
    ) -> SearchResult:
        try:
            query = canonical_external_query(query)
        except ExternalQueryError as exc:
            raise SearchError(str(exc)) from None
        allowed = _domains(domains)
        limit = self.settings.max_results if max_results is None else max_results
        try:
            query_bytes = len(query.encode("utf-8")) if isinstance(query, str) else 0
        except UnicodeError:
            raise SearchError("invalid_query") from None
        if (
            not isinstance(query, str)
            or not query.strip()
            or query_bytes > 4096
            or type(limit) is not int
            or not 1 <= limit <= self.settings.max_results
        ):
            raise SearchError("invalid_query")
        body = await self._post(
            "search",
            {
                "query": query,
                "search_depth": "basic",
                "max_results": limit,
                "include_domains": list(allowed),
                "include_domains_mode": "restrict",
                "include_answer": False,
                "include_raw_content": False,
                "auto_parameters": False,
                "include_usage": True,
            },
            budget,
        )
        sources, limitations = self._sources(body, "content", "search_snippet", allowed, None)
        return SearchResult(sources, _credits(body), limitations)

    async def extract(
        self, urls: tuple[str, ...], *, domains: tuple[str, ...], budget: SearchBudget
    ) -> ExtractResult:
        allowed = _domains(domains)
        if not 1 <= len(urls) <= 5:
            raise SearchError("invalid_source")
        checked = tuple(dict.fromkeys(checked_source_url(url, allowed) for url in urls))
        body = await self._post(
            "extract",
            {
                "urls": list(checked),
                "extract_depth": "basic",
                "format": "markdown",
                "include_images": False,
                "include_usage": True,
            },
            budget,
        )
        sources, limitations = self._sources(
            body, "raw_content", "extracted_page", allowed, set(checked)
        )
        returned = {item.url for item in sources}
        failures = tuple(
            ExtractFailure(url, "extraction_failed") for url in checked if url not in returned
        )
        return ExtractResult(sources, failures, _credits(body), limitations)

    async def _post(
        self, operation: str, payload: dict[str, object], budget: SearchBudget
    ) -> dict[str, object]:
        budget.reserve()
        try:
            async with asyncio.timeout(self.settings.timeout_seconds):
                async with httpx.AsyncClient(
                    timeout=self.settings.timeout_seconds,
                    transport=self.transport,
                    follow_redirects=False,
                    trust_env=False,
                ) as client:
                    async with client.stream(
                        "POST",
                        "https://api.tavily.com/" + operation,
                        headers={
                            "Authorization": "Bearer " + self.settings.api_key.get_secret_value()
                        },
                        json=payload,
                    ) as response:
                        if response.status_code != 200:
                            status = response.status_code
                            reason = (
                                "unauthorized"
                                if status in (401, 403)
                                else "rate_limited"
                                if status == 429
                                else "quota_exhausted"
                                if status in (402, 432, 433)
                                else "provider_error"
                            )
                            raise SearchError(reason)
                        data = bytearray()
                        async for chunk in response.aiter_bytes():
                            data.extend(chunk)
                            if len(data) > self.settings.max_response_bytes:
                                raise SearchError("response_too_large")
                        body = json.loads(data)
        except (httpx.TimeoutException, TimeoutError):
            raise SearchError("timeout") from None
        except httpx.HTTPError:
            raise SearchError("provider_error") from None
        except (ValueError, UnicodeError):
            raise SearchError("invalid_response") from None
        if not isinstance(body, dict):
            raise SearchError("invalid_response")
        budget.settle(_credits(body))
        return body

    def _sources(
        self,
        body: dict[str, object],
        content_key: str,
        scope: Literal["search_snippet", "extracted_page"],
        domains: tuple[str, ...],
        requested: set[str] | None,
    ) -> tuple[tuple[WebSource, ...], tuple[str, ...]]:
        rows = body.get("results")
        if not isinstance(rows, list):
            raise SearchError("invalid_response")
        found: list[WebSource] = []
        limitations: list[str] = []
        for row in rows[: self.settings.max_results if requested is None else 5]:
            if not isinstance(row, dict):
                raise SearchError("invalid_response")
            try:
                url = checked_source_url(row.get("url"), domains)
            except SearchError:
                limitations.append("out_of_scope_result")
                continue
            if requested is not None and url not in requested:
                limitations.append("unexpected_result")
                continue
            content = row.get(content_key)
            if not isinstance(content, str) or not content.strip():
                limitations.append("empty_content")
                continue
            truncated = len(content) > self.settings.max_content_chars
            content = content[: self.settings.max_content_chars]
            found.append(
                WebSource(
                    url,
                    row.get("title") if isinstance(row.get("title"), str) else None,
                    content,
                    scope,
                    datetime.now(UTC).isoformat(),
                    hashlib.sha256(content.encode()).hexdigest(),
                    row.get("published_date")
                    if isinstance(row.get("published_date"), str)
                    else None,
                    ("content_truncated",) if truncated else (),
                )
            )
        return tuple(found), tuple(dict.fromkeys(limitations))


def _credits(body: dict[str, object]) -> int | None:
    usage = body.get("usage")
    value = usage.get("credits") if isinstance(usage, dict) else None
    return value if type(value) is int and value >= 0 else None
