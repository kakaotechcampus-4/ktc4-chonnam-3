"""미지원 사이트 폴백. parse_error_code='unsupported_site'.
사람인(view-detail, 본문이 이미지 PNG) · 잡코리아(엔드포인트 미발견) 는 Sprint 2.

확정본 §3 / 2차
"""

from app.integrations.jd.base import (
    FetchedPosting,
    JdRequirementItem,
    JdUnsupportedSite,
)


class GenericAdapter:
    """항상 차단한다. 공고 없이 진행하는 경로는 만들지 않는다."""

    name = "generic"

    def matches(self, url: str) -> bool:  # noqa: ARG002 - 폴백은 항상 마지막
        return True

    def normalize(self, url: str) -> str:
        return url.split("?", 1)[0].rstrip("/")

    async def fetch(self, url: str) -> FetchedPosting:
        raise JdUnsupportedSite(url)

    def extract_requirements(self, posting: FetchedPosting) -> list[JdRequirementItem]:
        raise JdUnsupportedSite(posting.normalized_url)
