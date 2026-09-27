"""Wanted 자료의 재사용·불변 참조·동시 저장을 실제 PostgreSQL로 검증한다."""

import asyncio
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.db.base import Base
from app.db.models import AnalysisJob, InterviewSession, JdRequirement, JobPosting, User
from app.integrations.jd.base import PostingUnreachableError, UnsupportedSiteError
from app.llm_tasks.jd_extract import JdExtractionError

URL = "https://www.wanted.co.kr/wd/123456"
NOW = datetime(2026, 9, 28, 12, tzinfo=UTC)
PAYLOAD = {
    "job": {
        "detail": {
            "position": "백엔드 개발자",
            "intro": "결제 서비스를 만듭니다.",
            "requirements": ["Python 경험"],
            "preferred_points": ["Redis 경험"],
            "main_tasks": ["API 개발"],
        },
        "company": {"name": "예시회사", "industry_name": "핀테크"},
        "skill_tags": [{"text": "Python"}, {"text": "Redis"}],
    }
}


def _service():
    # 구현 전에도 collection을 완료해 누락된 기능을 명시적인 실패로 확인한다.
    import importlib.util

    name = "app.features.analysis.posting_service"
    assert importlib.util.find_spec(name) is not None, "공고 저장 service가 필요하다"
    from app.features.analysis.posting_service import get_or_fetch_posting

    return get_or_fetch_posting


@pytest.mark.parametrize(
    "url",
    [URL, "http://wanted.co.kr/wd/123456?tracking=1#role", "https://www.wanted.co.kr/wd/123456/"],
)
def test_normalization_uses_verified_wanted_id(url):
    _service()
    from app.features.analysis.posting_service import normalize_posting_url

    assert normalize_posting_url(url) == URL


@pytest.fixture
async def posting_sessions(test_database_url):
    schema = f"test_postings_{uuid4().hex}"
    engine = create_async_engine(
        test_database_url,
        poolclass=NullPool,
        connect_args={"server_settings": {"search_path": schema, "statement_timeout": "15000"}},
    )
    try:
        async with engine.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            await connection.run_sync(Base.metadata.create_all)
        yield async_sessionmaker(engine, expire_on_commit=True)
    finally:
        async with engine.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await engine.dispose()


async def _fetch(sessions, *, payload=PAYLOAD, now=NOW, url=URL):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    ) as client:
        return await _service()(sessions, url, client=client, now=now)


async def _requirements(sessions, posting_id):
    async with sessions() as db:
        return list(
            await db.scalars(
                select(JdRequirement)
                .where(JdRequirement.job_posting_id == posting_id)
                .order_by(JdRequirement.display_order)
            )
        )


async def test_first_fetch_persists_source_groups_and_requirement_categories(posting_sessions):
    result = await _fetch(posting_sessions, url="http://wanted.co.kr/wd/123456?track=test#section")
    assert result.normalized_url == URL
    assert result.source_posting_id == "123456"
    assert result.position == "백엔드 개발자"
    assert result.company_name == "예시회사"
    assert result.domain_category is None
    assert result.fetched_at == NOW
    assert result.raw_payload["requirements"] == ["Python 경험"]
    assert result.raw_payload["preferred_points"] == ["Redis 경험"]
    assert result.raw_payload["main_tasks"] == ["API 개발"]
    assert result.raw_payload["industry"] == "핀테크"
    requirements = await _requirements(posting_sessions, result.id)
    assert [(r.category, r.text, r.display_order) for r in requirements] == [
        ("required", "Python 경험", 0),
        ("preferred", "Redis 경험", 1),
        ("responsibility", "API 개발", 2),
    ]
    assert all(r.tech_tags == ["Python", "Redis"] for r in requirements)


@pytest.mark.parametrize("age", [timedelta(days=6), timedelta(days=7)])
async def test_fresh_cache_skips_http_and_does_not_extend_freshness(posting_sessions, age):
    first = await _fetch(posting_sessions)

    def unexpected_http(request):
        pytest.fail("7일 이내 성공 자료는 HTTP를 호출하면 안 된다")

    async with httpx.AsyncClient(transport=httpx.MockTransport(unexpected_http)) as client:
        cached = await _service()(posting_sessions, URL, client=client, now=NOW + age)
    assert cached.id == first.id
    assert cached.fetched_at == NOW
    assert cached.created_at == first.created_at


async def test_expired_same_content_preserves_ids_and_refreshes_only_check_time(posting_sessions):
    first = await _fetch(posting_sessions)
    before = await _requirements(posting_sessions, first.id)
    later = NOW + timedelta(days=7, microseconds=1)
    reused = await _fetch(posting_sessions, now=later, url=URL + "?different=tracking")
    assert reused.id == first.id
    assert reused.fetched_at == later
    assert reused.created_at == first.created_at
    assert reused.raw_url == first.raw_url
    assert reused.raw_payload == first.raw_payload
    assert [r.id for r in await _requirements(posting_sessions, first.id)] == [r.id for r in before]


async def test_changed_content_creates_new_ids_without_rewriting_run_or_interview(posting_sessions):
    first = await _fetch(posting_sessions)
    requirements = await _requirements(posting_sessions, first.id)
    async with posting_sessions.begin() as db:
        user = User(name="공고 참조 검증")
        db.add(user)
        await db.flush()
        run = AnalysisJob(
            user_id=user.id, job_type="analysis_run", status="succeeded", job_posting_id=first.id
        )
        db.add(run)
        await db.flush()
        interview = InterviewSession(
            user_id=user.id, analysis_job_id=run.id, job_posting_id=first.id
        )
        db.add(interview)
        await db.flush()
        run_id, interview_id = run.id, interview.id
    changed = deepcopy(PAYLOAD)
    changed["job"]["detail"]["requirements"] = ["Go 경험"]
    new = await _fetch(posting_sessions, payload=changed, now=NOW + timedelta(days=8))
    assert new.id != first.id
    assert (await _requirements(posting_sessions, new.id))[0].text == "Go 경험"
    assert [r.id for r in await _requirements(posting_sessions, first.id)] == [
        r.id for r in requirements
    ]
    async with posting_sessions() as db:
        assert (await db.get(AnalysisJob, run_id)).job_posting_id == first.id
        assert (await db.get(InterviewSession, interview_id)).job_posting_id == first.id
        old = await db.get(JobPosting, first.id)
        assert old.fetched_at == NOW
        assert old.raw_payload == first.raw_payload


@pytest.mark.parametrize("existing", [False, True])
async def test_concurrent_first_or_expired_fetch_commits_one_snapshot(posting_sessions, existing):
    first = await _fetch(posting_sessions) if existing else None
    now = NOW + timedelta(days=8)
    changed = deepcopy(PAYLOAD)
    changed["job"]["detail"]["requirements"] = ["Go 경험"]
    arrived = 0
    both_fetching = asyncio.Event()

    async def respond(request):
        nonlocal arrived
        arrived += 1
        if arrived == 2:
            both_fetching.set()
        await asyncio.wait_for(both_fetching.wait(), timeout=5)
        return httpx.Response(200, json=changed)

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        results = await asyncio.wait_for(
            asyncio.gather(
                *(_service()(posting_sessions, URL, client=client, now=now) for _ in range(2))
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


@pytest.mark.parametrize("extract_failure", [False, True])
async def test_failed_refresh_keeps_prior_success_and_records_failed_attempt(
    posting_sessions, extract_failure
):
    first = await _fetch(posting_sessions)
    body = {"job": {"detail": {"position": "내용만 있고 요구사항 없음"}}}
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200 if extract_failure else 503, json=body)
        )
    ) as client:
        with pytest.raises(JdExtractionError if extract_failure else PostingUnreachableError):
            await _service()(posting_sessions, URL, client=client, now=NOW + timedelta(days=8))
    async with posting_sessions() as db:
        previous = await db.get(JobPosting, first.id)
        assert previous.parse_status == "succeeded"
        assert previous.fetched_at == NOW
        assert previous.raw_payload == first.raw_payload
        failed = await db.scalar(select(JobPosting).where(JobPosting.parse_status == "failed"))
        assert failed.parse_error_code == (
            "jd_extraction_failed" if extract_failure else "jd_fetch_failed"
        )
    assert len(await _requirements(posting_sessions, first.id)) == 3


async def test_unsupported_site_never_creates_posting(posting_sessions):
    with pytest.raises(UnsupportedSiteError):
        await _service()(posting_sessions, "https://example.com/wd/123456", now=NOW)
    async with posting_sessions() as db:
        assert await db.scalar(select(func.count()).select_from(JobPosting)) == 0


async def test_requirement_write_failure_rolls_back_parent_posting(posting_sessions):
    async with posting_sessions.begin() as db:
        await db.execute(
            text("""
            CREATE FUNCTION reject_requirement() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'intentional requirement failure'; END $$
        """)
        )
        await db.execute(
            text("""
            CREATE TRIGGER reject_requirement BEFORE INSERT ON jd_requirements
            FOR EACH ROW EXECUTE FUNCTION reject_requirement()
        """)
        )
    with pytest.raises(DBAPIError, match="intentional requirement failure"):
        await _fetch(posting_sessions)
    async with posting_sessions() as db:
        assert await db.scalar(select(func.count()).select_from(JobPosting)) == 0
        assert await db.scalar(select(func.count()).select_from(JdRequirement)) == 0
