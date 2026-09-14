"""source_url → site_adapter 선택. 미지원 사이트는 unsupported_site.
site_adapter 컬럼이 어댑터별 성공률 비교 축이므로 어떤 어댑터를 썼는지 반드시 기록한다.

확정본 §3 job_postings / task-09
"""

from app.integrations.jd.base import JdAdapter, JdUnsupportedSite
from app.integrations.jd.wanted import WantedAdapter


def resolve_adapter(url: str) -> JdAdapter:
    """Sprint 1 은 Wanted 만 지원한다. 나머지는 즉시 차단(400 unsupported_site)."""
    candidate = url.strip()
    if not candidate:
        raise JdUnsupportedSite(url)
    adapter = WantedAdapter()
    if adapter.matches(candidate):
        return adapter
    raise JdUnsupportedSite(url)


def is_supported(url: str) -> bool:
    """job 생성 전에 400 으로 거를 수 있는지 판단한다."""
    try:
        resolve_adapter(url)
    except JdUnsupportedSite:
        return False
    return True


def normalize_posting_url(url: str) -> str:
    """job_postings 재사용 판정과 run fingerprint 에 쓰는 정규 URL."""
    return resolve_adapter(url).normalize(url.strip())
