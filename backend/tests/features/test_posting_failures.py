"""실패 기록 재사용과 과거 참조 보존을 실제 PostgreSQL로 검증한다."""

import asyncio
from datetime import timedelta

import httpx
import pytest
from sqlalchemy import select

from app.db.models import AnalysisJob, InterviewSession, JobPosting, User
from app.features.analysis.posting_service import (
    complete_posting,
    fetch_posting,
    get_or_fetch_posting,
)
from app.integrations.jd.base import PostingUnreachableError
from app.llm_tasks.jd_extract import JdExtractionError
from tests.features.test_postings import NOW, PAYLOAD, URL, _fetch, _requirements
from tests.features.test_postings import posting_sessions as posting_sessions

UNSTRUCTURED = {
    "job": {
        "detail": {"position": "요구사항이 없는 공고", "intro": "회사 소개만 있습니다."},
        "company": {"name": "실패 기록 회사"},
        "skill_tags": [{"text": "Python"}],
    }
}


async def _fail(sessions, *, now=NOW, extract=False, url=URL):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200 if extract else 503, json=UNSTRUCTURED)
        )
    ) as client:
        with pytest.raises(JdExtractionError if extract else PostingUnreachableError):
            await get_or_fetch_posting(sessions, url, client=client, now=now)


async def _failures(sessions):
    async with sessions() as db:
        return list(await db.scalars(select(JobPosting).where(JobPosting.parse_status == "failed")))


@pytest.mark.parametrize("extract", [False, True])
async def test_repeated_failure_reuses_row_updates_time_and_preserves_success(
    posting_sessions, extract
):
    successful = await _fetch(posting_sessions)
    requirements = await _requirements(posting_sessions, successful.id)
    first_attempt = NOW + timedelta(days=8)
    await _fail(posting_sessions, now=first_attempt, extract=extract)
    first = (await _failures(posting_sessions))[0]
    assert first.updated_at == first_attempt

    calls = 0

    def respond(request):
        nonlocal calls
        calls += 1
        return httpx.Response(200 if extract else 503, json=UNSTRUCTURED)

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        for attempt in (1, 2):
            with pytest.raises(JdExtractionError if extract else PostingUnreachableError):
                await get_or_fetch_posting(
                    posting_sessions,
                    URL,
                    client=client,
                    now=first_attempt + timedelta(minutes=attempt),
                )

    # 실패 기록은 저장만 재사용하며, 장애가 해소됐는지 HTTP로 다시 확인한다.
    assert calls == 2
    failed = await _failures(posting_sessions)
    assert len(failed) == 1 and failed[0].id == first.id
    assert failed[0].created_at == first.created_at
    assert failed[0].updated_at == first_attempt + timedelta(minutes=2)
    assert failed[0].parse_error_code == ("jd_extraction_failed" if extract else "jd_fetch_failed")
    async with posting_sessions() as db:
        previous = await db.get(JobPosting, successful.id)
        assert previous.parse_status == "succeeded"
        assert previous.fetched_at == NOW and previous.raw_payload == successful.raw_payload
    assert [item.id for item in await _requirements(posting_sessions, successful.id)] == [
        item.id for item in requirements
    ]


async def test_concurrent_failures_commit_one_record(posting_sessions):
    arrived = 0
    both_fetching = asyncio.Event()

    async def respond(request):
        nonlocal arrived
        arrived += 1
        if arrived == 2:
            both_fetching.set()
        await asyncio.wait_for(both_fetching.wait(), timeout=5)
        return httpx.Response(503)

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        results = await asyncio.wait_for(
            asyncio.gather(
                *(
                    get_or_fetch_posting(posting_sessions, URL, client=client, now=NOW)
                    for _ in range(2)
                ),
                return_exceptions=True,
            ),
            timeout=10,
        )
    assert arrived == 2
    assert all(isinstance(item, PostingUnreachableError) for item in results)
    failed = await _failures(posting_sessions)
    assert len(failed) == 1 and failed[0].updated_at == NOW


async def test_late_concurrent_failure_does_not_hide_new_success(posting_sessions):
    failed_fetch_started = asyncio.Event()
    success_saved = asyncio.Event()

    async def success_response(request):
        await asyncio.wait_for(failed_fetch_started.wait(), timeout=5)
        return httpx.Response(200, json=PAYLOAD)

    async def failure_response(request):
        failed_fetch_started.set()
        # 두 요청 모두 캐시 조회를 마친 뒤 성공 저장보다 실패 응답이 늦게 도착하게 한다.
        await asyncio.wait_for(success_saved.wait(), timeout=5)
        return httpx.Response(503)

    async with (
        httpx.AsyncClient(transport=httpx.MockTransport(success_response)) as success_client,
        httpx.AsyncClient(transport=httpx.MockTransport(failure_response)) as failure_client,
    ):

        async def succeed():
            result = await get_or_fetch_posting(
                posting_sessions, URL, client=success_client, now=NOW
            )
            success_saved.set()
            return result

        successful, error = await asyncio.wait_for(
            asyncio.gather(
                succeed(),
                get_or_fetch_posting(posting_sessions, URL, client=failure_client, now=NOW),
                return_exceptions=True,
            ),
            timeout=10,
        )
    assert isinstance(successful, JobPosting) and isinstance(error, PostingUnreachableError)
    assert len(await _failures(posting_sessions)) == 1

    def unexpected_http(request):
        pytest.fail("늦은 실패 기록이 정상 자료 재사용을 막으면 안 된다")

    async with httpx.AsyncClient(transport=httpx.MockTransport(unexpected_http)) as client:
        cached = await get_or_fetch_posting(posting_sessions, URL, client=client, now=NOW)
    assert cached.id == successful.id and cached.parse_status == "succeeded"
    assert cached.fetched_at == NOW
    assert len(await _requirements(posting_sessions, cached.id)) == 3


async def test_fetch_failure_clears_previous_extraction_content(posting_sessions):
    await _fail(posting_sessions, extract=True)
    previous = (await _failures(posting_sessions))[0]
    assert previous.raw_payload and previous.fetched_at == NOW
    assert previous.position and previous.company_name and previous.skill_tags

    later = NOW + timedelta(minutes=1)
    await _fail(posting_sessions, now=later)

    failed = await _failures(posting_sessions)
    assert len(failed) == 1 and failed[0].id == previous.id
    assert failed[0].parse_error_code == "jd_fetch_failed"
    assert failed[0].raw_payload is None and failed[0].fetched_at is None
    assert failed[0].position is None and failed[0].company_name is None
    assert failed[0].skill_tags == [] and failed[0].updated_at == later


async def test_late_older_extraction_failure_does_not_replace_newer_failure(posting_sessions):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=UNSTRUCTURED))
    ) as client:
        older = await fetch_posting(posting_sessions, URL, client=client, now=NOW)
    later = NOW + timedelta(minutes=1)
    await _fail(posting_sessions, now=later)
    previous = (await _failures(posting_sessions))[0]

    # 먼저 수집한 요청이 늦게 끝나도 최근 실패의 상태·시각을 되돌리지 않는다.
    with pytest.raises(JdExtractionError):
        await complete_posting(posting_sessions, older)

    failed = await _failures(posting_sessions)
    assert len(failed) == 1 and failed[0].id == previous.id
    assert failed[0].parse_error_code == "jd_fetch_failed"
    assert failed[0].updated_at == later and failed[0].raw_payload is None


async def test_recovery_creates_success_without_rewriting_failure(posting_sessions):
    await _fail(posting_sessions)
    failed = (await _failures(posting_sessions))[0]
    recovered = await _fetch(posting_sessions, payload=PAYLOAD, now=NOW + timedelta(minutes=1))

    assert recovered.id != failed.id and recovered.parse_status == "succeeded"
    assert len(await _requirements(posting_sessions, recovered.id)) == 3
    remaining = await _failures(posting_sessions)
    assert len(remaining) == 1 and remaining[0].id == failed.id
    assert remaining[0].updated_at == failed.updated_at
    assert remaining[0].parse_error_code == "jd_fetch_failed"


@pytest.mark.parametrize("reference", ["analysis", "interview"])
async def test_referenced_failure_is_preserved_and_only_unreferenced_row_reused(
    posting_sessions, reference
):
    await _fail(posting_sessions, extract=True)
    original = (await _failures(posting_sessions))[0]
    async with posting_sessions.begin() as db:
        user = User(name="실패 자료 참조 검증")
        db.add(user)
        await db.flush()
        run = AnalysisJob(
            user_id=user.id,
            job_type="analysis_run",
            status="failed",
            job_posting_id=original.id if reference == "analysis" else None,
        )
        db.add(run)
        await db.flush()
        run_id = run.id
        interview_id = None
        if reference == "interview":
            interview = InterviewSession(
                user_id=user.id, analysis_job_id=run.id, job_posting_id=original.id
            )
            db.add(interview)
            await db.flush()
            interview_id = interview.id

    await _fail(posting_sessions, now=NOW + timedelta(minutes=1))
    await _fail(posting_sessions, now=NOW + timedelta(minutes=2))

    failed = await _failures(posting_sessions)
    assert len(failed) == 2
    preserved = next(item for item in failed if item.id == original.id)
    reusable = next(item for item in failed if item.id != original.id)
    assert preserved.parse_error_code == "jd_extraction_failed"
    assert preserved.raw_payload == original.raw_payload
    assert preserved.fetched_at == original.fetched_at
    assert preserved.updated_at == original.updated_at
    assert reusable.parse_error_code == "jd_fetch_failed"
    assert reusable.updated_at == NOW + timedelta(minutes=2)
    async with posting_sessions() as db:
        if reference == "analysis":
            assert (await db.get(AnalysisJob, run_id)).job_posting_id == original.id
        else:
            assert (await db.get(InterviewSession, interview_id)).job_posting_id == original.id


async def test_failure_reuse_does_not_cross_normalized_urls(posting_sessions):
    await _fail(posting_sessions)
    await _fail(posting_sessions, url="https://www.wanted.co.kr/wd/654321")
    await _fail(posting_sessions, now=NOW + timedelta(minutes=1))

    failed = await _failures(posting_sessions)
    assert len(failed) == 2
    assert {item.normalized_url for item in failed} == {
        URL,
        "https://www.wanted.co.kr/wd/654321",
    }
    assert next(item for item in failed if item.normalized_url == URL).updated_at == (
        NOW + timedelta(minutes=1)
    )
