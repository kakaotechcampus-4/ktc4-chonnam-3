"""미지원 사이트 폴백. parse_error_code='unsupported_site'.
사람인(view-detail, 본문이 이미지 PNG) · 잡코리아(엔드포인트 미발견) 는 2차.

확정본 §3 / 2차
"""

from __future__ import annotations

from app.integrations.jd.base import PostingContent, UnsupportedSiteError


class GenericAdapter:
    """1차에는 실제 수집을 하지 않고 항상 unsupported_site 로 떨어뜨리는 폴백.

    2차에서 사람인·잡코리아 크롤링(또는 헤드리스 브라우저)을 붙일 자리.
    """

    site_adapter = "generic"

    async def fetch(self, url: str) -> PostingContent:
        raise UnsupportedSiteError(f"1차는 원티드만 지원함: {url}")
