"""공고 사이트 어댑터 프로토콜. fetch(url) → FetchedPosting. DB 를 모른다.

확정본 §3 site_adapter / task-09
"""

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


class JdFetchError(RuntimeError):
    """수집 실패. parse_error_code='jd_fetch_failed' 로 이어진다."""


class JdUnsupportedSite(RuntimeError):
    """지원하지 않는 사이트. 공고 없이 진행으로 유도하지 않고 차단한다."""


@dataclass(frozen=True)
class JdRequirementItem:
    """구조화 필드에서 뽑은 요구사항 1줄. LLM 을 쓰지 않는 결정적 변환 결과다."""

    requirement_type: str
    text: str
    tech_tags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class FetchedPosting:
    """어댑터 수집 결과. job_postings 1행으로 그대로 옮길 수 있는 형태."""

    site_adapter: str
    fetch_url: str
    normalized_url: str
    external_id: str | None
    position: str | None
    company_name: str | None
    raw_text: str
    raw_json: dict[str, Any] | None = None
    source_image_urls: list[str] = field(default_factory=list)
    skill_tags: list[str] = field(default_factory=list)
    content_form: str = "text"


@runtime_checkable
class JdAdapter(Protocol):
    """사이트별 어댑터. 어떤 어댑터를 썼는지 반드시 기록한다."""

    name: str

    def matches(self, url: str) -> bool:
        """이 어댑터가 처리할 URL 인지."""
        ...

    def normalize(self, url: str) -> str:
        """재사용 판정에 쓰는 정규 URL."""
        ...

    async def fetch(self, url: str) -> FetchedPosting:
        """공고 수집. 실패는 JdFetchError."""
        ...

    def extract_requirements(self, posting: FetchedPosting) -> list[JdRequirementItem]:
        """구조화 필드 -> 요구사항 목록 (결정적 변환, LLM 없음)."""
        ...
