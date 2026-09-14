"""공고 사이트 어댑터 프로토콜. fetch(url) → (fetch_url, raw_text, image_urls, content_form).
DB 를 모른다.

확정본 §3 site_adapter / task-09
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True, slots=True)
class PostingContent:
    """어댑터가 공고 페이지에서 얻어낸 원본 내용.

    `site_adapter`가 이미 항목별로 필드를 분리해 주는 경우(예: 원티드)에는
    ``requirements`` / ``preferred_points`` / ``main_tasks`` / ``skill_tags`` 를 채운다 —
    이 필드들이 채워져 있으면 jd_extract 단계는 LLM 을 호출하지 않고 그대로 매핑한다.
    구조화된 필드를 못 주는 어댑터(제너릭 폴백)는 ``raw_text`` 만 채우고 나머지는 빈 값으로 둔다.
    """

    site_adapter: str
    """어댑터 식별자. `job_postings.site_adapter` 에 그대로 저장된다. 예: "wanted", "generic"."""

    fetch_url: str
    """실제로 요청을 보낸 최종 URL (리다이렉트 반영)."""

    content_form: str
    """"text" | "image" | "mixed". `job_postings.content_form` CHECK 값과 동일해야 한다."""

    raw_text: str = ""
    """구조화 실패 시에도 항상 채워지는 대표 텍스트 (구조화 필드가 있으면 이어붙인 요약)."""

    image_urls: list[str] = field(default_factory=list)

    position: str | None = None
    company_name: str | None = None
    industry: str | None = None

    requirements: list[str] = field(default_factory=list)
    """필수 요건 — `jd_requirements.category='required'` 원천."""

    preferred_points: list[str] = field(default_factory=list)
    """우대 사항 — `category='preferred'` 원천."""

    main_tasks: list[str] = field(default_factory=list)
    """주요 업무 — `category='responsibility'` 원천."""

    skill_tags: list[str] = field(default_factory=list)
    """어댑터가 이미 정규화해 준 기술 태그. `jd_requirements.tech_tags` 원천이라
    LLM 의 기술명 추측이 불필요하다 (원티드 한정)."""

    @property
    def is_structured(self) -> bool:
        """requirements/preferred_points/main_tasks 가 이미 항목별로 분리돼 왔는지.

        True 면 jd_extract 단계는 LLM 을 호출하지 않고 그대로 매핑한다."""
        return bool(self.requirements or self.preferred_points or self.main_tasks)


class PostingFetchError(Exception):
    """공고 수집 실패 공통 베이스. `.code` 는 `job_postings.parse_error_code` 값과 동일하다.

    docs/error-reasons.md ④ 참고 — `unsupported_site`/`url_unreachable`/`content_empty` 는
    "우리 코드" 실패라 재시도해도 소용없다. `not_a_job_posting`/`extraction_failed`/
    `llm_timeout` 은 LLM 단계(jd_extract)에서 별도로 발생하므로 여기서는 다루지 않는다.
    """

    code: str

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.code)


class UnsupportedSiteError(PostingFetchError):
    code = "unsupported_site"


class PostingUnreachableError(PostingFetchError):
    code = "url_unreachable"


class PostingContentEmptyError(PostingFetchError):
    code = "content_empty"


class JdAdapter(Protocol):
    """공고 사이트별 어댑터가 구현해야 하는 인터페이스."""

    site_adapter: str

    async def fetch(self, url: str) -> PostingContent:
        """`url` 에서 공고 내용을 가져온다.

        Raises:
            UnsupportedSiteError: 이 어댑터가 다룰 수 없는 URL.
            PostingUnreachableError: 404·마감·네트워크 실패.
            PostingContentEmptyError: 텍스트·이미지 둘 다 없음.
        """
        ...
