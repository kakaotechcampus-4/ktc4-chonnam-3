"""Link 헤더 파서. rel='last' 의 page=N 을 뽑는다.
commit_count / user_commit_count 를 얻는 유일한 수단 (전체 커밋을 받지 않기 위해).

확정본 §2 M2 비용 최적화 / task-08

`?per_page=1` 로 한 건만 받고 rel='last' 의 page 값을 읽으면 그게 전체 개수다.
커밋이 3천 개인 레포에서 3천 건을 받지 않아도 된다.
"""

import re
from urllib.parse import parse_qs, urlparse

# <https://api.github.com/...?page=42>; rel="last"
_LINK_PART = re.compile(r'<(?P<url>[^>]+)>\s*;\s*rel="(?P<rel>[^"]+)"')


def parse_link_header(header: str | None) -> dict[str, str]:
    """Link 헤더를 {rel: url} 로 만든다.

    입력: Link 헤더 문자열(없으면 None). 출력: rel 이름과 URL 의 dict.
    """
    if not header:
        return {}
    return {match.group("rel"): match.group("url") for match in _LINK_PART.finditer(header)}


def page_of(url: str) -> int | None:
    """URL 의 page 쿼리 값을 읽는다. 입력: URL. 출력: page 번호, 없거나 숫자가 아니면 None."""
    values = parse_qs(urlparse(url).query).get("page")
    if not values:
        return None
    try:
        return int(values[0])
    except ValueError:
        return None


def last_page(header: str | None) -> int | None:
    """Link 헤더에서 마지막 page 번호를 뽑는다.

    입력: Link 헤더. 출력: rel='last' 의 page 번호, 없으면 None.
    페이지가 1장뿐이면 GitHub 이 rel='last' 를 주지 않으므로 None 이 정상이다.
    """
    links = parse_link_header(header)
    last = links.get("last")
    return page_of(last) if last is not None else None


def total_from_per_page_one(header: str | None, returned_items: int) -> int:
    """`per_page=1` 요청의 전체 개수를 구한다.

    입력: Link 헤더, 이번 응답이 돌려준 항목 수.
    출력: 전체 개수.

    rel='last' 가 있으면 그 page 번호가 곧 전체 개수다 (한 page 에 1건씩이므로).
    없으면 페이지가 1장뿐이라는 뜻이라 받은 항목 수가 전체다 — 0건이면 0이다.
    """
    page = last_page(header)
    if page is not None:
        return page
    return returned_items
