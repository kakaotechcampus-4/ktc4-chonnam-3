"""공고 사이트 어댑터 프로토콜. fetch(url) → PostingContent
DB 모름

확정본 §3 site_adapter / task-09
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True, slots=True)
class PostingContent:
    """어댑터가 공고 페이지에서 얻어낸 원본 내용

    `site_adapter`가 이미 항목별로 필드를 분리해 주는 경우(예: 원티드)에는
    ``requirements`` / ``preferred_points`` / ``main_tasks`` / ``skill_tags`` 를 채움 —
    이 필드들이 채워져 있으면 jd_extract 단계는 LLM 호출 없이 그대로 매핑함
    향후 비구조화 어댑터는 ``raw_text``를 사용할 수 있다.
    현재 제너릭 어댑터는 본문을 수집하지 않고 미지원 사이트 오류를 발생시킨다.
    """

    site_adapter: str
    """어댑터 식별자. `job_postings.site_adapter` 에 그대로 저장됨. 예: "wanted", "generic\""""

    fetch_url: str
    """공고 수집에 요청한 URL"""

    content_form: str
    """"text" | "image" | "mixed". `job_postings.content_form` CHECK 값과 동일"""

    raw_text: str = ""
    """구조화 실패 시에도 항상 채워지는 대표 텍스트 (구조화 필드가 있으면 이어붙인 요약)"""

    image_urls: list[str] = field(default_factory=list)

    position: str | None = None
    company_name: str | None = None
    industry: str | None = None

    requirements: list[str] = field(default_factory=list)
    """필수 요건 — API category와 DB requirement_type 모두 required"""

    preferred_points: list[str] = field(default_factory=list)
    """우대 사항 — API category와 DB requirement_type 모두 preferred"""

    main_tasks: list[str] = field(default_factory=list)
    """주요 업무 — API category는 responsibility, DB requirement_type은 unknown"""

    skill_tags: list[str] = field(default_factory=list)
    """어댑터가 이미 정규화해 준 기술 태그. `jd_requirements.tech_tags` 원천이라
    LLM 의 기술명 추측 불필요 (원티드 한정)"""

    @property
    def is_structured(self) -> bool:
        """requirements/preferred_points/main_tasks 가 이미 항목별로 분리돼 왔는지

        True 면 jd_extract 단계는 LLM 호출 없이 그대로 매핑"""
        return bool(self.requirements or self.preferred_points or self.main_tasks)


class PostingFetchError(Exception):
    """공고 수집 실패 공통 베이스. `.code` 는 `job_postings.parse_error_code` 값과 동일

    docs/error-reasons.md ④ 참고. 어댑터의 네트워크·응답·빈 본문 실패는 모두
    `jd_fetch_failed` 로 저장한다. `unsupported_site` 는 별도 계약 코드다.
    """

    code: str

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.code)


class UnsupportedSiteError(PostingFetchError):
    code = "unsupported_site"


class PostingUnreachableError(PostingFetchError):
    """HTTP·네트워크 오류 또는 JSON 해석 실패로 공고를 읽지 못한 경우."""

    code = "jd_fetch_failed"


class PostingContentEmptyError(PostingFetchError):
    """응답은 받았지만 사용할 공고 본문이 없는 경우."""

    code = "jd_fetch_failed"


class PostingInvalidResponseError(PostingFetchError):
    """응답 구조나 필드 타입이 달라 공고 내용을 신뢰할 수 없는 경우."""

    code = "jd_fetch_failed"


class JdAdapter(Protocol):
    """공고 사이트별 어댑터가 구현해야 하는 인터페이스"""

    site_adapter: str

    async def fetch(self, url: str) -> PostingContent:
        """`url` 에서 공고 내용을 가져옴. 마감 공고도 본문에 접근 가능하면 수집한다.

        Raises:
            UnsupportedSiteError: 이 어댑터가 다룰 수 없는 URL
            PostingUnreachableError: HTTP 오류·네트워크 실패·JSON 해석 실패
            PostingContentEmptyError: 텍스트·이미지 둘 다 없음
            PostingInvalidResponseError: 외부 응답 구조나 필드 타입이 올바르지 않음
        """
        ...
