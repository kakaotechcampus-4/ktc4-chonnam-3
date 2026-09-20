"""미지원 사이트 폴백. parse_error_code='unsupported_site'.
사람인(view-detail, 본문이 이미지 PNG) · 잡코리아(엔드포인트 미발견) 는 2차.

확정본 §3 / 2차

Sprint 1 은 unsupported site 를 차단한다. 공고 없이 진행으로 유도하지 않는다
(spec/backend/features/analysis-run.md — 공고는 hard blocker).
"""

from app.integrations.jd.base import (
    JD_ERROR_UNSUPPORTED_SITE,
    JdFetchResult,
    failure,
)


class GenericAdapter:
    """어느 어댑터도 받지 않은 URL 을 받는 마지막 어댑터.

    항상 unsupported_site 로 실패한다. 존재 이유는 두 가지다.
    - resolver 가 None 을 돌려주지 않게 해서 호출부의 분기를 줄인다
    - site_adapter 컬럼에 'generic' 이 쌓여 어떤 사이트가 얼마나 요청되는지 보인다
    """

    name = "generic"

    def supports(self, url: str) -> bool:
        """언제나 True. 어댑터 목록의 맨 뒤에만 둔다."""
        return True

    def normalize_url(self, url: str) -> str | None:
        """정규화하지 않는다. 미지원 사이트는 job_postings 행을 만들지 않는다."""
        return None

    async def fetch(self, url: str) -> JdFetchResult:
        """항상 unsupported_site 로 실패한다. 입력: 원본 URL. 출력: JdFetchResult."""
        return failure(self.name, JD_ERROR_UNSUPPORTED_SITE)
