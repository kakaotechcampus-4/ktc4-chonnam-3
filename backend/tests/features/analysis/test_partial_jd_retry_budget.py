"""부분 성공의 원문을 보존하면서 이미지 재호출을 유한한 주기로 제한한다."""

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select

from app.core.config import Settings
from app.db.models import JdRequirement, JobPosting
from app.features.analysis import posting_service as service
from app.features.analysis.image_jd import ImageDrafts
from app.integrations.jd.base import PostingContent
from app.integrations.vision.elice import VisionResult
from app.llm_tasks.jd_extract import JdExtractionError

URL = "https://www.wanted.co.kr/wd/123"
NOW = datetime(2026, 11, 10, tzinfo=UTC)


def source():
    return PostingContent(
        "wanted",
        URL,
        "mixed",
        position="개발자",
        requirements=["Python 개발 경험"],
        image_urls=["https://static.wanted.co.kr/jd.png"],
        skill_tags=["Python"],
    )


async def saved_partial(sessions, content=None):
    content = content or source()
    async with sessions.begin() as db:
        row = service._posting(URL, URL, content, NOW - timedelta(minutes=3))
        row.domain_category = "finance"
        row.raw_payload = {
            **row.raw_payload,
            "_image_extraction": {"status": "failed"},
            "_domain_classification": {"status": "succeeded", "evidence": "원문 근거"},
            "_image_retry": {
                "attempts": 1,
                "cycle_started_at": (NOW - timedelta(minutes=3)).isoformat(),
                "next_retry_at": (NOW - timedelta(minutes=2)).isoformat(),
            },
        }
        db.add(row)
        await db.flush()
        requirement = JdRequirement(
            job_posting_id=row.id,
            category="required",
            text="Python 개발 경험",
            tech_tags=["Python"],
            display_order=0,
        )
        db.add(requirement)
        await db.flush()
        return row.id, requirement.id


async def test_concurrent_partial_retry_commits_one_attempt_before_the_only_vision_call(
    session_factory, monkeypatch
):
    entered, release = asyncio.Event(), asyncio.Event()
    vision_calls, observed = [], []

    class Vision:
        def __init__(self, settings):
            self.settings = settings

        async def extract(self, *args, **kwargs):
            vision_calls.append(1)
            # 실제 공급자 진입 시 이미 예약이 commit됐고 URL lock은 풀려 있어야 한다.
            async with session_factory.begin() as db:
                await service.lock_posting_url(db, URL)
                row = await db.get(JobPosting, identity)
                observed.append(dict(row.raw_payload["_image_retry"]))
            entered.set()
            await release.wait()
            return VisionResult("fixture", (), 1, {})

    monkeypatch.setattr("app.integrations.jd.images.EliceVisionClient", Vision)

    def http(request):
        if request.url.host == "static.wanted.co.kr":
            return httpx.Response(
                200, content=b"\x89PNG\r\n\x1a\nx", headers={"Content-Type": "image/png"}
            )
        return httpx.Response(
            200,
            json={
                "job": {
                    "detail": {
                        "position": "개발자",
                        "requirements": ["Python 개발 경험"],
                        "image_urls": source().image_urls,
                    }
                }
            },
        )

    settings = Settings(
        _env_file=None, vision_base_url="https://vision.invalid", vision_api_key="fixture"
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(http)) as client:
        # 과거 저장본과 재수집본은 같은 어댑터의 원문으로 만든다. 표시용 필드 차이를
        # 실제 원문 변경으로 혼동하는 인위적인 fixture를 사용하지 않는다.
        original = await service.WantedAdapter(client=client).fetch(URL)
        identity, requirement_id = await saved_partial(session_factory, original)
        first = asyncio.create_task(
            service.get_or_fetch_posting(
                session_factory,
                URL,
                client=client,
                now=NOW,
                settings=settings,
            )
        )
        await asyncio.wait_for(entered.wait(), 5)
        try:
            second = await asyncio.wait_for(
                service.get_or_fetch_posting(
                    session_factory,
                    URL,
                    client=client,
                    now=NOW,
                    settings=settings,
                ),
                5,
            )
            assert second.id == identity
            assert second.domain_category == "finance"
            assert len(vision_calls) == 1
            assert observed[0]["attempts"] == 2 and observed[0]["owner"]
            assert datetime.fromisoformat(observed[0]["lease_expires_at"]) > NOW
        finally:
            release.set()
            await asyncio.wait_for(first, 5)
    async with session_factory() as db:
        row = await db.get(JobPosting, identity)
        assert row.domain_category == "finance"
        assert row.raw_payload["_domain_classification"]["evidence"] == "원문 근거"
        assert (await db.get(JdRequirement, requirement_id)).text == "Python 개발 경험"


async def test_failed_attempt_is_counted_before_http_and_obeys_cooldown_and_hour_cap(
    session_factory, monkeypatch
):
    identity, _ = await saved_partial(session_factory)
    calls = []

    async def failed(*args, **kwargs):
        calls.append(1)
        raise JdExtractionError("jd_extraction_failed", "fixture")

    monkeypatch.setattr(service, "extend_image_drafts", failed)
    prepared = service.PreparedPosting(URL, URL, NOW, 7, content=source())
    with pytest.raises(JdExtractionError):
        await service.complete_posting(session_factory, prepared)
    async with session_factory() as db:
        state = (await db.get(JobPosting, identity)).raw_payload["_image_retry"]
        assert state["attempts"] == 2 and "owner" not in state
        assert state["last_error"] == "jd_extraction_failed"
    assert (await service.complete_posting(session_factory, prepared)).id == identity
    later = replace(prepared, checked_at=NOW + timedelta(seconds=121))
    with pytest.raises(JdExtractionError):
        await service.complete_posting(session_factory, later)
    assert (
        await service.complete_posting(
            session_factory, replace(prepared, checked_at=NOW + timedelta(minutes=30))
        )
    ).id == identity
    assert len(calls) == 2
    async with session_factory() as db:
        state = (await db.get(JobPosting, identity)).raw_payload["_image_retry"]
        assert state["attempts"] == 3


async def test_changed_source_gets_a_new_budget_and_complete_success_removes_retry_state(
    session_factory, monkeypatch
):
    identity, _ = await saved_partial(session_factory)

    async def partial(sessions, content, drafts, **kwargs):
        return ImageDrafts(
            replace(content, source_metadata={"image_extraction": {"status": "partial"}}),
            drafts,
            [[] for _ in drafts],
        )

    monkeypatch.setattr(service, "extend_image_drafts", partial)
    content = replace(source(), position="다른 개발자")
    first = await service.complete_posting(
        session_factory, service.PreparedPosting(URL, URL, NOW, 7, content=content)
    )
    assert first.id != identity and first.raw_payload["_image_retry"]["attempts"] == 1

    async def complete(sessions, content, drafts, **kwargs):
        return ImageDrafts(
            replace(content, source_metadata={"image_extraction": {"status": "succeeded"}}),
            drafts,
            [[] for _ in drafts],
        )

    monkeypatch.setattr(service, "extend_image_drafts", complete)
    result = await service.complete_posting(
        session_factory,
        service.PreparedPosting(URL, URL, NOW + timedelta(seconds=61), 7, content=content),
    )
    assert "_image_retry" not in result.raw_payload
    assert result.parse_status == "succeeded"


async def test_unrelated_fetch_failure_cannot_erase_an_initial_image_attempt_budget(
    session_factory, monkeypatch
):
    calls = []

    async def failed(*args, **kwargs):
        calls.append(1)
        raise JdExtractionError("jd_extraction_failed", "fixture")

    monkeypatch.setattr(service, "extend_image_drafts", failed)
    prepared = service.PreparedPosting(URL, URL, NOW, 7, content=source())
    with pytest.raises(JdExtractionError):
        await service.complete_posting(session_factory, prepared)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(503))
    ) as http:
        with pytest.raises(service.PostingFetchError):
            await service.fetch_posting(
                session_factory, URL, client=http, now=NOW + timedelta(seconds=10)
            )
    with pytest.raises(JdExtractionError):
        await service.complete_posting(
            session_factory, replace(prepared, checked_at=NOW + timedelta(seconds=20))
        )
    assert calls == [1]
    async with session_factory() as db:
        rows = list(await db.scalars(select(JobPosting)))
        budget = [
            row.raw_payload["_image_retry"]
            for row in rows
            if isinstance(row.raw_payload, dict) and "_image_retry" in row.raw_payload
        ]
        assert len(budget) == 1 and budget[0]["attempts"] == 1
