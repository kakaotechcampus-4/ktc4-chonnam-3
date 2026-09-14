"""Link 헤더 파서. rel='last' 의 page=N 을 뽑는다.
commit_count / user_commit_count 를 얻는 유일한 수단 (전체 커밋을 받지 않기 위해).

확정본 §2 M2 비용 최적화 / task-08
"""

import re
from urllib.parse import parse_qs, urlparse

_LINK_PART = re.compile(r'<(?P<url>[^>]+)>\s*;\s*rel="(?P<rel>[^"]+)"')


def parse_link_header(header: str | None) -> dict[str, str]:
    """`<url>; rel="next", <url>; rel="last"` -> {rel: url}."""
    if not header:
        return {}
    return {m.group("rel"): m.group("url") for m in _LINK_PART.finditer(header)}


def last_page_number(header: str | None) -> int | None:
    """rel='last' 의 page 값. 링크가 없으면 None (= 페이지가 1개거나 결과가 없음)."""
    last = parse_link_header(header).get("last")
    if not last:
        return None
    pages = parse_qs(urlparse(last).query).get("page")
    if not pages:
        return None
    try:
        return int(pages[0])
    except ValueError:
        return None


def total_count_from_single_page(header: str | None, first_page_items: int) -> int:
    """`per_page=1` 응답에서 전체 개수를 계산한다.

    rel='last' 가 있으면 그 page 번호가 곧 전체 개수이고, 없으면 첫 페이지 항목 수다.
    """
    last = last_page_number(header)
    return last if last is not None else first_page_items
