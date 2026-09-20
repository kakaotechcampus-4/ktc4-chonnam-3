"""source_url → site_adapter 선택. 미지원 사이트는 unsupported_site.
site_adapter 컬럼이 어댑터별 성공률 비교 축이므로 어떤 어댑터를 썼는지 반드시 기록한다.

확정본 §3 job_postings / task-09
"""

from collections.abc import Sequence

import httpx

from app.integrations.jd.base import JdFetchResult, JobPostingAdapter
from app.integrations.jd.generic import GenericAdapter
from app.integrations.jd.wanted import WantedAdapter


def default_adapters(
    *,
    client: httpx.AsyncClient | None = None,
    requirement_limit: int | None = None,
) -> tuple[JobPostingAdapter, ...]:
    """Sprint 1 어댑터 목록. 입력: 주입할 client·상한. 출력: 어댑터 튜플.

    GenericAdapter 는 항상 True 를 돌려주므로 반드시 맨 뒤에 둔다.
    호출마다 새로 만든다 — 어댑터가 상태를 공유하지 않게 한다.
    """
    wanted = (
        WantedAdapter(client=client, requirement_limit=requirement_limit)
        if requirement_limit is not None
        else WantedAdapter(client=client)
    )
    return (wanted, GenericAdapter())


def resolve_adapter(
    url: str,
    adapters: Sequence[JobPostingAdapter] | None = None,
) -> JobPostingAdapter:
    """URL 을 받을 어댑터를 고른다.

    입력: 원본 URL, 어댑터 목록(기본은 default_adapters()).
    출력: JobPostingAdapter. 맞는 어댑터가 없으면 GenericAdapter 가 잡으므로 None 이 아니다.
    """
    for adapter in adapters if adapters is not None else default_adapters():
        if adapter.supports(url):
            return adapter
    # default_adapters() 를 쓰면 도달하지 않는다. 직접 넘긴 목록이 비었을 때의 안전망이다.
    return GenericAdapter()


def normalize_posting_url(
    url: str,
    adapters: Sequence[JobPostingAdapter] | None = None,
) -> str | None:
    """재사용 판정에 쓸 정규 URL 을 만든다.

    입력: 원본 URL, 어댑터 목록. 출력: 정규 URL, 지원하지 않는 사이트면 None.
    service 는 이 값으로 job_postings 를 조회해 fetched_at 24시간 이내면 재사용한다.
    """
    return resolve_adapter(url, adapters).normalize_url(url)


async def fetch_job_posting(
    url: str,
    adapters: Sequence[JobPostingAdapter] | None = None,
) -> JdFetchResult:
    """어댑터를 골라 공고를 가져온다.

    입력: 원본 URL, 어댑터 목록. 출력: JdFetchResult.
    결과의 adapter 에 어떤 어댑터를 썼는지 항상 담긴다 — 실패해도 마찬가지다.
    """
    return await resolve_adapter(url, adapters).fetch(url)
