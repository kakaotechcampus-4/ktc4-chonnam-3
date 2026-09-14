"""source_url → site_adapter 선택. 미지원 사이트는 unsupported_site.
site_adapter 컬럼이 어댑터별 성공률 비교 축이므로 어떤 어댑터를 썼는지 반드시 기록한다.

확정본 §3 job_postings / task-09
"""

from __future__ import annotations

from urllib.parse import urlparse

import httpx

from app.integrations.jd.base import JdAdapter, UnsupportedSiteError
from app.integrations.jd.generic import GenericAdapter
from app.integrations.jd.wanted import WantedAdapter

_WANTED_HOSTS = {"www.wanted.co.kr", "wanted.co.kr"}


def resolve_adapter(url: str, *, client: httpx.AsyncClient | None = None) -> JdAdapter:
    """URL 의 호스트를 보고 담당 어댑터를 고른다. 못 고르면 `UnsupportedSiteError`.

    `job_postings.site_adapter` 는 실제로 fetch 를 수행한 어댑터가
    (`WantedAdapter.site_adapter` 등으로) 알려주므로, 여기서는 "어떤 어댑터 *클래스*를
    쓸지"만 결정한다 — GenericAdapter 도 골라진 뒤 즉시 unsupported_site 로 실패하지만,
    그 실패 자체가 하나의 site_adapter='generic' 시도 기록이다.
    """
    host = urlparse(url).hostname or ""

    if host in _WANTED_HOSTS:
        return WantedAdapter(client=client)

    if not host:
        raise UnsupportedSiteError(f"URL에서 호스트를 못 찾음: {url}")

    return GenericAdapter()
