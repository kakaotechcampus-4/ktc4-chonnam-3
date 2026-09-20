"""공고 사이트 어댑터 프로토콜. fetch(url) → (fetch_url, raw_text, image_urls, content_form).
DB 를 모른다.

확정본 §3 site_adapter / task-09

어댑터는 HTTP 호출과 구조화까지만 한다. job_postings 재사용 판정(fetched_at 24시간)과
행 저장은 service 가 한다.
"""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol

from app.shared.enums import JdCategory

# job_postings.parse_error_code (docs/error-reasons.md)
JD_ERROR_UNSUPPORTED_SITE = "unsupported_site"
JD_ERROR_FETCH_FAILED = "jd_fetch_failed"
JD_ERROR_EXTRACTION_FAILED = "jd_extraction_failed"
JD_ERROR_NOT_A_JOB_POSTING = "not_a_job_posting"


class ContentForm(StrEnum):
    """본문이 글자로 오는지 이미지로 오는지.

    Sprint 1 의 Wanted 는 text 다. 본문이 이미지인 사이트(사람인 등)는 Sprint 2 다.
    """

    TEXT = "text"
    IMAGE = "image"


class JdParseStatus(StrEnum):
    """공고 수집 결과. job_postings.parse_status 와 같은 값이다."""

    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class JdRequirementItem:
    """요구사항 한 줄. jd_requirements 행 하나가 된다."""

    category: JdCategory
    text: str
    display_order: int


@dataclass(frozen=True, slots=True)
class JobPostingPayload:
    """어댑터가 만든 공고 한 건. service 가 job_postings 로 옮긴다."""

    source: str
    normalized_url: str
    raw_url: str
    # 실제로 호출한 주소. 어댑터별 성공률을 비교할 때 무엇을 쳤는지 알아야 한다.
    fetch_url: str
    source_posting_id: str | None = None
    position: str | None = None
    company_name: str | None = None
    skill_tags: list[str] = field(default_factory=list)
    requirements: list[JdRequirementItem] = field(default_factory=list)
    content_form: ContentForm = ContentForm.TEXT
    image_urls: list[str] = field(default_factory=list)
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class JdFetchResult:
    """어댑터 호출 결과.

    adapter 는 실패해도 반드시 채운다 — site_adapter 컬럼이 어댑터별 성공률 비교 축이다.
    """

    adapter: str
    status: JdParseStatus
    payload: JobPostingPayload | None = None
    error_code: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.status is not JdParseStatus.FAILED


class JobPostingAdapter(Protocol):
    """공고 사이트 어댑터. Sprint 1 구현체는 Wanted 하나뿐이다."""

    name: str

    def supports(self, url: str) -> bool:
        """이 어댑터가 처리할 URL 인지. 입력: 원본 URL. 출력: bool."""
        ...

    def normalize_url(self, url: str) -> str | None:
        """재사용 판정에 쓸 정규 URL. 입력: 원본 URL. 출력: 정규 URL, 못 만들면 None."""
        ...

    async def fetch(self, url: str) -> JdFetchResult:
        """공고를 가져와 구조화한다. 입력: 원본 URL. 출력: JdFetchResult."""
        ...


def failure(adapter: str, error_code: str) -> JdFetchResult:
    """실패 결과를 만든다. 입력: 어댑터 이름, error_code. 출력: JdFetchResult."""
    return JdFetchResult(adapter=adapter, status=JdParseStatus.FAILED, error_code=error_code)
