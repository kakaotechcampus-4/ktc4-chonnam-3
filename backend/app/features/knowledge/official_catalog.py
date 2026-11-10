"""공식 URL은 접근 범위이며, 질의·버전·언어·요청 절 검증을 대신하지 않는다."""

import hashlib
import json
import re
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from app.integrations.search.tavily import WebSource, checked_source_url

COMMON_DOMAINS = ("developer.mozilla.org", "docs.python.org")
# 수집 원문과 모델에 전달할 절은 별도 예산으로 제한한다.
MAX_PAGE_CONTENT_CHARS = 196608
MAX_SECTION_CONTENT_CHARS = 24000
OFFICIAL_DOMAINS = {
    "finance": ("developers.kftc.or.kr", "openbanking.or.kr"),
    "game": ("partner.steamgames.com",),
    "travel": ("data.go.kr", "api.visitkorea.or.kr"),
    "shopping": ("apicenter.commerce.naver.com",),
    "medical": ("hl7.org",),
    "mobility": ("gtfs.org",),
    "etc": ("elice.io",),
}
_TECHNOLOGIES = {
    "python": ("python", "asyncio", "파이썬"),
    "http": ("http", "429", "retry-after"),
    "redis": ("redis",),
    "openbanking": ("openbanking", "open banking", "오픈뱅킹"),
    "steam": ("steam", "steamworks"),
    "tourapi": ("tourapi", "관광"),
    "commerce": ("commerce", "커머스", "네이버"),
    "fhir": ("fhir",),
    "gtfs": ("gtfs",),
    "spring": ("spring",),
    "react": ("react",),
    "kubernetes": ("kubernetes", "k8s"),
    "java": ("java",),
    "javascript": ("javascript",),
    "typescript": ("typescript",),
    "postgresql": ("postgresql", "postgres"),
    "mysql": ("mysql",),
}
_STOP = frozenset(
    (
        "official documentation document docs reference verify failure concept details "
        "please explain english version the and for with from this what how does should "
        "using source sources"
    ).split()
)
_HEAD = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_CONCEPTS = {
    "cancellation": ("cancel", "취소"),
    "balance": ("balance", "잔액"),
    "authentication": ("authentication", "인증"),
    "security": ("security", "보안"),
    "session": ("session", "세션"),
    "architecture": ("architecture", "구조", "아키텍처"),
    "isolation": ("isolation", "격리"),
    "transaction": ("transaction", "트랜잭션"),
    "arrival_time": ("arrival_time", "도착시간", "도착시각"),
    "departure_time": ("departure_time", "출발시간", "출발시각"),
}
_KO_STOP = frozenset(
    (
        "공식 문서 설명 설명해 설명해주세요 알려주세요 어떻게 무엇인가요 동작 동작을 처리 "
        "원리 관련 자료 확인 방법 요청 영어 한국어 질문"
    ).split()
)


class OfficialSourceError(ValueError):
    """원문·접속정보를 포함하지 않는 수집 실패 사유."""


@dataclass(frozen=True)
class CatalogEntry:
    catalog_key: str
    domain_categories: tuple[str, ...]
    technology: str
    version: str
    language: str
    url: str
    section_heading: str
    query_terms: tuple[str, ...]
    availability: str
    verified_at: str
    limitations: tuple[str, ...]

    @property
    def definition_hash(self) -> str:
        values = asdict(self)
        # 검증 시각·설명 갱신은 기존 인용을 무효화하지 않는다. 접근 정책은 포함한다.
        values.pop("verified_at")
        values.pop("limitations")
        return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()


@dataclass(frozen=True)
class SnapshotDraft:
    entry: CatalogEntry
    url: str
    title: str | None
    content: str
    content_hash: str
    page_content: str
    page_content_hash: str
    start_line: int
    end_line: int
    retrieved_at: str
    limitations: tuple[str, ...]


def scope_domains(category: str | None) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            (*OFFICIAL_DOMAINS.get(category or "etc", OFFICIAL_DOMAINS["etc"]), *COMMON_DOMAINS)
        )
    )


def load_catalog() -> tuple[CatalogEntry, ...]:
    try:
        content = Path(__file__).with_name("official_catalog.json").read_text("utf-8")
        if len(content) > 131072:
            raise OfficialSourceError("catalog_invalid")
        return _parse_catalog(content)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        raise OfficialSourceError("catalog_invalid") from exc


@lru_cache(maxsize=4)
def _parse_catalog(content: str) -> tuple[CatalogEntry, ...]:
    # 파일 내용이 캐시 키여서 수정·테스트 격리 시 이전 항목을 잘못 재사용하지 않는다.
    raw = json.loads(content)
    if (
        not isinstance(raw, dict)
        or raw.get("version") != "official-catalog.v1"
        or not isinstance(raw.get("sources"), list)
    ):
        raise OfficialSourceError("catalog_invalid")
    result = []
    for value in raw["sources"]:
        if not isinstance(value, dict):
            raise OfficialSourceError("catalog_invalid")
        item = CatalogEntry(
            **{
                **value,
                "domain_categories": tuple(value["domain_categories"]),
                "query_terms": tuple(value["query_terms"]),
                "limitations": tuple(value["limitations"]),
            }
        )
        allowed = tuple(
            dict.fromkeys(
                domain for category in item.domain_categories for domain in scope_domains(category)
            )
        )
        checked_source_url(item.url, allowed)
        if (
            not item.section_heading
            or item.technology not in _TECHNOLOGIES
            or not set(item.domain_categories) <= {*OFFICIAL_DOMAINS, "general"}
            or item.availability
            not in {"public_verified", "javascript_required", "login_required", "unverified"}
        ):
            raise OfficialSourceError("catalog_invalid")
        result.append(item)
    if len(result) > 64 or len({item.catalog_key for item in result}) != len(result):
        raise OfficialSourceError("catalog_invalid")
    return tuple(result)


def _query_version(query: str) -> str | None:
    found = re.search(
        r"\b(?:python|fhir|openbanking|open banking|gtfs|steam|commerce|spring(?:\s+boot)?|"
        r"react|kubernetes|java|javascript|typescript|postgresql|mysql|redis)"
        r"\s*(?:version\s+)?v?(\d+(?:\.\d+)*)\b",
        query,
        re.I,
    )
    if found:
        return found[1]
    http_version = re.search(r"\bhttp\s*(\d+\.\d+)\b", query, re.I)
    if http_version:
        return http_version[1]
    return "4.0.1" if re.search(r"\bfhir\s+r4\b", query, re.I) else None


def _language(query: str) -> str | None:
    if re.search(r"한국어|\bkorean\b|\bko-KR\b", query, re.I):
        return "ko"
    # 질문 작성 언어는 원문 언어 제한이 아니다. 명시한 언어만 제한한다.
    return "en" if re.search(r"\benglish\b", query, re.I) else None


def _source_language(source: WebSource) -> str | None:
    path = urlsplit(source.url).path
    found = re.match(r"/(en|fr|de|es|ja|ko|zh)(?:[-_][A-Za-z]+)?/", path)
    if found:
        return found[1]
    if urlsplit(source.url).hostname in {
        "docs.python.org",
        "hl7.org",
        "gtfs.org",
        "partner.steamgames.com",
    }:
        return "en"
    return None


def _has_alias(text: str, alias: str) -> bool:
    if re.search(r"[가-힣]", alias):
        return alias in text
    # Java와 JavaScript, 단어 안에 우연히 들어 있는 기술 이름을 구분한다.
    suffix = r"(?![a-z0-9_])" if alias[-1:].isdigit() else r"(?![a-z_])"
    return re.search(r"(?<![a-z0-9_])" + re.escape(alias) + suffix, text) is not None


def source_matches_query(
    query: str,
    source: WebSource,
    *,
    technology: str | None = None,
    version: str | None = None,
    language: str | None = None,
) -> tuple[bool, tuple[str, ...]]:
    body = source.content.casefold()
    requested = _query_version(query)
    observed = version
    if observed is None and urlsplit(source.url).hostname == "docs.python.org":
        found = re.search(r"/(\d+\.\d+)(?:/|$)", urlsplit(source.url).path)
        observed = found[1] if found else None
    if requested and (
        observed is None or not (requested == observed or observed.startswith(requested + "."))
    ):
        return False, ("source_version_mismatch",)
    wanted_language, observed_language = _language(query), language or _source_language(source)
    if wanted_language and observed_language and wanted_language != observed_language:
        return False, ("source_language_mismatch",)
    technologies = [
        key
        for key, aliases in _TECHNOLOGIES.items()
        if any(_has_alias(query.casefold(), alias) for alias in aliases)
    ]
    if technology and technology not in technologies:
        return False, ("query_technology_mismatch",)
    identity = f"{source.url} {source.title or ''} {body}".casefold()
    if any(
        not any(_has_alias(identity, alias) for alias in _TECHNOLOGIES[key]) for key in technologies
    ):
        return False, ("query_technology_mismatch",)
    # 명시 API 식별자를 빼먹은 같은 도메인 문서를 관련 자료로 채택하지 않는다.
    identifiers = re.findall(r"\b[A-Z][a-z]+(?:[A-Z][A-Za-z]*)+\b", query)
    if any(identifier.casefold() not in body for identifier in identifiers):
        return False, ("query_identifiers_missing",)
    aliases = {alias for key in technologies for alias in _TECHNOLOGIES[key]} - {
        "429",
        "retry-after",
    }
    terms = [
        term
        for term in re.findall(r"[a-z][a-z0-9_.-]{2,}|[가-힣]{2,}|\b[1-5]\d{2}\b", query.casefold())
        if term not in _STOP and term not in aliases and term not in _KO_STOP
    ]

    expanded: list[str] = []
    for term in terms:
        concepts = [
            concept
            for concept, spellings in _CONCEPTS.items()
            if re.search(r"[가-힣]", term) and term in spellings
        ]
        # 알려진 한영 개념만 대응시킨다. 알 수 없는 질의어는 계속 원문에서 확인한다.
        expanded.extend(concepts or (term,))
    terms = list(dict.fromkeys(expanded))

    def present(term: str) -> bool:
        return (
            term in body
            or any(alias in body for alias in _CONCEPTS.get(term, ()))
            or term in {"cancelled", "cancels"}
            and "cancel" in body
        )

    if not terms or not all(present(term) for term in terms):
        return False, ("query_terms_missing",)
    return True, (
        ("deterministic_query_match_not_semantic_approval",)
        + (() if observed_language else ("source_language_unverified",))
    )


def matching_entries(query: str, category: str | None) -> tuple[CatalogEntry, ...]:
    return tuple(
        item
        for item in load_catalog()
        if item.availability == "public_verified"
        and (category in item.domain_categories or "general" in item.domain_categories)
        and any(_has_alias(query.casefold(), alias) for alias in _TECHNOLOGIES[item.technology])
        and any(term.casefold() in query.casefold() for term in item.query_terms)
        and (
            _query_version(query) is None
            or item.version == _query_version(query)
            or item.version.startswith((_query_version(query) or "") + ".")
        )
        and (_language(query) is None or item.language == _language(query))
    )


def _heading(value: str) -> str:
    value = re.sub(r"\[¶\]\([^)]*\)", "", value)
    # 실제 추출의 [제목](#anchor)은 표시 문자열로만 대조하고 저장 원문은 바꾸지 않는다.
    value = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", value)
    return re.sub(r"\s+", " ", re.sub(r"[¶​]", "", value)).strip().casefold()


def _headings(lines: list[str]) -> Iterator[tuple[int, re.Match[str]]]:
    fence: str | None = None
    for index, line in enumerate(lines):
        marker = _FENCE.match(line)
        if marker:
            if fence is None:
                fence = marker[1]
            elif marker[1][0] == fence[0] and len(marker[1]) >= len(fence):
                fence = None
            continue
        if fence is None and (heading := _HEAD.match(line)):
            yield index, heading


def prepare_snapshot(entry: CatalogEntry, source: WebSource) -> SnapshotDraft:
    if source.content_scope != "extracted_page" or entry.availability != "public_verified":
        raise OfficialSourceError("source_not_extractable")
    if len(source.content) > MAX_PAGE_CONTENT_CHARS:
        raise OfficialSourceError("source_content_budget")
    if hashlib.sha256(source.content.encode()).hexdigest() != source.content_hash:
        raise OfficialSourceError("source_hash_mismatch")
    if _source_language(source) and _source_language(source) != entry.language:
        raise OfficialSourceError("source_language_mismatch")
    if entry.technology == "python" and f"/{entry.version}/" not in source.url:
        raise OfficialSourceError("source_version_mismatch")
    allowed = tuple(
        dict.fromkeys(
            domain for category in entry.domain_categories for domain in scope_domains(category)
        )
    )
    url = checked_source_url(entry.url, allowed)
    if checked_source_url(source.url, allowed) != url:
        raise OfficialSourceError("source_url_mismatch")
    lines = source.content.splitlines()
    headings = list(_headings(lines))
    starts = [
        (i, match) for i, match in headings if _heading(match[2]) == _heading(entry.section_heading)
    ]
    if len(starts) != 1:
        raise OfficialSourceError("requested_section_missing")
    start, heading = starts[0]
    end = next(
        (i for i, match in headings if i > start and len(match[1]) <= len(heading[1])),
        len(lines),
    )
    if end == len(lines) and "content_truncated" in source.limitations:
        raise OfficialSourceError("requested_section_incomplete")
    if not any(
        line.strip() and not _HEAD.match(line) and not _FENCE.match(line)
        for line in lines[start + 1 : end]
    ):
        raise OfficialSourceError("requested_section_empty")
    content = "\n".join(lines[start:end]).rstrip()
    if len(content) > MAX_SECTION_CONTENT_CHARS:
        raise OfficialSourceError("section_content_budget")
    return SnapshotDraft(
        entry,
        url,
        source.title,
        content,
        hashlib.sha256(content.encode()).hexdigest(),
        source.content,
        source.content_hash,
        start + 1,
        start + len(content.splitlines()),
        source.retrieved_at,
        tuple(
            dict.fromkeys(
                (*entry.limitations, *source.limitations, "line_coordinates_extracted_markdown")
            )
        ),
    )
