"""공고 수집·추출의 단계 경계와 분리된 저장의 일관성을 PostgreSQL로 검증한다."""

import asyncio
from copy import deepcopy
from datetime import timedelta
from unittest.mock import MagicMock

import httpx
import pytest
from sqlalchemy import func, select

from app.db.models import JdRequirement, JobPosting
from app.features.analysis import posting_service
from app.integrations.jd.base import PostingUnreachableError
from app.llm_tasks.jd_extract import JdExtractionError
from tests.features.test_postings import NOW, PAYLOAD, URL, _fetch, _requirements
from tests.features.test_postings import posting_sessions as posting_sessions


async def _prepare(sessions, *, payload=PAYLOAD, now=NOW):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    ) as client:
        return await posting_service.fetch_posting(sessions, URL, client=client, now=now)


async def test_fetch_releases_transaction_and_defers_extraction_and_success_write(
    posting_sessions, monkeypatch
):
    queried_sessions = []
    current_posting = posting_service.get_current_successful_posting

    async def current(db, url):
        queried_sessions.append(db)
        return await current_posting(db, url)

    def respond(request):
        assert queried_sessions and not queried_sessions[-1].in_transaction()
        return httpx.Response(200, json=PAYLOAD)

    extract = MagicMock(wraps=posting_service.build_requirement_drafts)
    monkeypatch.setattr(posting_service, "get_current_successful_posting", current)
    monkeypatch.setattr(posting_service, "build_requirement_drafts", extract)
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        prepared = await posting_service.fetch_posting(
            posting_sessions, URL, client=client, now=NOW
        )

    extract.assert_not_called()
    assert prepared.cached is None and prepared.content is not None
    async with posting_sessions() as db:
        assert await db.scalar(select(func.count()).select_from(JobPosting)) == 0
        assert await db.scalar(select(func.count()).select_from(JdRequirement)) == 0

    result = await posting_service.complete_posting(posting_sessions, prepared)

    extract.assert_called_once_with(prepared.content)
    assert result.parse_status == "succeeded" and result.fetched_at == NOW
    assert len(await _requirements(posting_sessions, result.id)) == 3


async def test_fetch_failure_is_recorded_without_extraction(posting_sessions, monkeypatch):
    extract = MagicMock(side_effect=AssertionError("수집 실패 뒤에는 추출하지 않는다"))
    monkeypatch.setattr(posting_service, "build_requirement_drafts", extract)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(503))
    ) as client:
        with pytest.raises(PostingUnreachableError):
            await posting_service.fetch_posting(posting_sessions, URL, client=client, now=NOW)

    extract.assert_not_called()
    async with posting_sessions() as db:
        failed = (await db.scalars(select(JobPosting))).one()
        assert failed.parse_status == "failed" and failed.parse_error_code == "jd_fetch_failed"
        assert failed.raw_payload is None and failed.fetched_at is None
        assert await db.scalar(select(func.count()).select_from(JdRequirement)) == 0


async def test_extraction_failure_belongs_to_complete_and_preserves_previous_success(
    posting_sessions,
):
    first = await _fetch(posting_sessions)
    prepared = await _prepare(
        posting_sessions,
        payload={"job": {"detail": {"position": "본문은 있지만 요구사항이 없음"}}},
        now=NOW + timedelta(days=8),
    )
    async with posting_sessions() as db:
        assert await db.scalar(select(func.count()).select_from(JobPosting)) == 1

    with pytest.raises(JdExtractionError, match="구조화되지 않은"):
        await posting_service.complete_posting(posting_sessions, prepared)

    async with posting_sessions() as db:
        previous = await db.get(JobPosting, first.id)
        assert previous.parse_status == "succeeded" and previous.fetched_at == NOW
        failed = await db.scalar(select(JobPosting).where(JobPosting.parse_status == "failed"))
        assert failed.parse_error_code == "jd_extraction_failed"
        assert failed.raw_payload["position"] == "본문은 있지만 요구사항이 없음"
        assert failed.fetched_at == NOW + timedelta(days=8)
    assert len(await _requirements(posting_sessions, first.id)) == 3


async def test_fresh_cache_skips_both_steps_without_extending_ttl(posting_sessions, monkeypatch):
    first = await _fetch(posting_sessions)
    extract = MagicMock(side_effect=AssertionError("캐시 재사용에는 추출이 필요하지 않다"))
    monkeypatch.setattr(posting_service, "build_requirement_drafts", extract)

    def unexpected_http(request):
        pytest.fail("7일 경계의 성공 캐시는 HTTP 없이 재사용해야 한다")

    async with httpx.AsyncClient(transport=httpx.MockTransport(unexpected_http)) as client:
        prepared = await posting_service.fetch_posting(
            posting_sessions, URL, client=client, now=NOW + timedelta(days=7)
        )
    result = await posting_service.complete_posting(posting_sessions, prepared)

    assert prepared.content is None and result is prepared.cached
    assert result.id == first.id and result.fetched_at == NOW
    extract.assert_not_called()


@pytest.mark.parametrize("existing", [False, True])
async def test_concurrent_completions_recheck_cache_under_url_lock(posting_sessions, existing):
    first = await _fetch(posting_sessions) if existing else None
    changed = deepcopy(PAYLOAD)
    changed["job"]["detail"]["requirements"] = ["Go 경험"]
    prepared = [
        await _prepare(posting_sessions, payload=changed, now=NOW + timedelta(days=8))
        for _ in range(2)
    ]
    assert all(item.cached is None for item in prepared)

    results = await asyncio.wait_for(
        asyncio.gather(
            *(posting_service.complete_posting(posting_sessions, item) for item in prepared)
        ),
        timeout=10,
    )

    assert results[0].id == results[1].id
    assert first is None or results[0].id != first.id
    async with posting_sessions() as db:
        assert await db.scalar(select(func.count()).select_from(JobPosting)) == (
            2 if existing else 1
        )
    assert len(await _requirements(posting_sessions, results[0].id)) == 3


async def test_unexpected_extraction_error_is_not_recorded_as_provider_failure(
    posting_sessions, monkeypatch
):
    prepared = await _prepare(posting_sessions)
    monkeypatch.setattr(
        posting_service, "build_requirement_drafts", MagicMock(side_effect=RuntimeError("bug"))
    )

    with pytest.raises(RuntimeError, match="bug"):
        await posting_service.complete_posting(posting_sessions, prepared)

    async with posting_sessions() as db:
        assert await db.scalar(select(func.count()).select_from(JobPosting)) == 0
