"""제목이 저장된 과거 캐시만 새 자료로 교체하고 기존 면접 참조를 보존한다."""

import asyncio
from copy import deepcopy
from dataclasses import asdict
from datetime import timedelta

import httpx
import pytest
from sqlalchemy import func, select

from app.db.models import (
    AnalysisJob,
    InterviewSession,
    InterviewTurn,
    JdRequirement,
    JobPosting,
    User,
)
from app.features.analysis import posting_service
from app.integrations.jd.base import PostingUnreachableError
from app.integrations.jd.wanted import WantedAdapter
from app.llm_tasks.jd_extract import JdExtractionError
from tests.features.test_postings import NOW, PAYLOAD, URL, _fetch, _requirements
from tests.features.test_postings import posting_sessions as posting_sessions


async def _content(payload):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    ) as client:
        return await WantedAdapter(client=client).fetch(URL)


async def _legacy(sessions, *, field="requirements", heading="필수 역량"):
    payload = deepcopy(PAYLOAD)
    payload["job"]["detail"][field].insert(0, heading)
    content = await _content(payload)
    # 새 추출기로 과거 오류를 감추지 않도록 당시 저장된 행을 그대로 준비한다.
    async with sessions.begin() as db:
        posting = posting_service._posting(URL, URL, content, NOW)
        db.add(posting)
        await db.flush()
        order = 0
        for category, source in (
            ("required", "requirements"),
            ("preferred", "preferred_points"),
            ("responsibility", "main_tasks"),
        ):
            for value in getattr(content, source):
                db.add(
                    JdRequirement(
                        job_posting_id=posting.id,
                        category=category,
                        text=value,
                        display_order=order,
                        tech_tags=list(content.skill_tags),
                    )
                )
                order += 1
        await db.flush()
        identity = posting.id
    return identity, payload, content


async def _snapshot(sessions, identity):
    async with sessions() as db:
        posting = await db.get(JobPosting, identity)
        rows = await posting_service.get_posting_requirements(db, identity)
        return {
            "posting": {
                column.key: getattr(posting, column.key)
                for column in posting.__mapper__.column_attrs
            },
            "requirements": [
                {column.key: getattr(row, column.key) for column in row.__mapper__.column_attrs}
                for row in rows
            ],
        }


async def _bind_old_interview(sessions, posting_id):
    async with sessions.begin() as db:
        user = User(name="과거 공고 참조 검증")
        db.add(user)
        await db.flush()
        run = AnalysisJob(
            user_id=user.id, job_type="analysis_run", status="succeeded", job_posting_id=posting_id
        )
        db.add(run)
        await db.flush()
        interview = InterviewSession(
            user_id=user.id, analysis_job_id=run.id, job_posting_id=posting_id
        )
        db.add(interview)
        await db.flush()
        ids = [row.id for row in await posting_service.get_posting_requirements(db, posting_id)]
        turn = InterviewTurn(
            interview_session_id=interview.id,
            turn_no=1,
            persona="hr_manager",
            question_text="기존 요구사항을 확인합니다.",
            jd_requirement_ids=ids,
        )
        db.add(turn)
        await db.flush()
        return run.id, interview.id, turn.id, ids


@pytest.mark.parametrize(
    ("field", "heading"),
    [
        ("requirements", "필수 역량"),
        ("preferred_points", "**우대사항:**"),
        ("main_tasks", "주요 역할"),
    ],
)
async def test_fresh_heading_cache_refetches_and_versions_without_changing_old_references(
    posting_sessions, field, heading
):
    previous, payload, _ = await _legacy(posting_sessions, field=field, heading=heading)
    before = await _snapshot(posting_sessions, previous)
    run_id, interview_id, turn_id, old_ids = await _bind_old_interview(posting_sessions, previous)
    calls = 0

    def respond(request):
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=payload)

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        result = await posting_service.get_or_fetch_posting(
            posting_sessions, URL, client=client, now=NOW + timedelta(days=1)
        )

    assert calls == 1
    assert result.id != previous
    assert result.raw_payload == before["posting"]["raw_payload"]
    assert [row.text for row in await _requirements(posting_sessions, result.id)] == [
        "Python 경험",
        "Redis 경험",
        "API 개발",
    ]
    assert await _snapshot(posting_sessions, previous) == before
    async with posting_sessions() as db:
        assert (await db.get(AnalysisJob, run_id)).job_posting_id == previous
        assert (await db.get(InterviewSession, interview_id)).job_posting_id == previous
        assert (await db.get(InterviewTurn, turn_id)).jd_requirement_ids == old_ids


async def test_complete_does_not_reuse_heading_cache_created_between_stages(posting_sessions):
    previous, _, content = await _legacy(posting_sessions)
    before = await _snapshot(posting_sessions, previous)
    prepared = posting_service.PreparedPosting(
        URL, URL, NOW + timedelta(days=1), 7, content=content
    )

    result = await posting_service.complete_posting(posting_sessions, prepared)

    assert result.id != previous
    assert result.raw_payload == asdict(content)
    assert len(await _requirements(posting_sessions, result.id)) == 3
    assert await _snapshot(posting_sessions, previous) == before


async def test_concurrent_heading_refresh_reuses_new_clean_snapshot_under_url_lock(
    posting_sessions,
):
    previous, _, content = await _legacy(posting_sessions)
    prepared = posting_service.PreparedPosting(
        URL, URL, NOW + timedelta(days=1), 7, content=content
    )

    results = await asyncio.wait_for(
        asyncio.gather(
            *(posting_service.complete_posting(posting_sessions, prepared) for _ in range(2))
        ),
        timeout=10,
    )

    assert results[0].id == results[1].id != previous
    async with posting_sessions() as db:
        assert await db.scalar(select(func.count()).select_from(JobPosting)) == 2
    assert len(await _requirements(posting_sessions, results[0].id)) == 3
    assert len(await _requirements(posting_sessions, previous)) == 4


@pytest.mark.parametrize("failure", ["fetch", "extract"])
async def test_failed_heading_refresh_preserves_previous_success_and_requirements(
    posting_sessions, failure
):
    previous, _, _ = await _legacy(posting_sessions)
    before = await _snapshot(posting_sessions, previous)
    payload = deepcopy(PAYLOAD)
    for field, label in (
        ("requirements", "필수 역량"),
        ("preferred_points", "우대사항"),
        ("main_tasks", "주요 역할"),
    ):
        payload["job"]["detail"][field] = [label]
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(503 if failure == "fetch" else 200, json=payload)
        )
    ) as client:
        with pytest.raises(PostingUnreachableError if failure == "fetch" else JdExtractionError):
            await posting_service.get_or_fetch_posting(
                posting_sessions, URL, client=client, now=NOW + timedelta(days=1)
            )

    assert await _snapshot(posting_sessions, previous) == before
    async with posting_sessions() as db:
        statuses = list(await db.scalars(select(JobPosting.parse_status)))
        assert sorted(statuses) == ["failed", "succeeded"]


async def test_normal_fresh_cache_still_avoids_http_and_keeps_ids(posting_sessions):
    previous = await _fetch(posting_sessions)
    before = await _snapshot(posting_sessions, previous.id)

    def unexpected_http(request):
        pytest.fail("정상 캐시는 새 수집 없이 재사용해야 한다")

    async with httpx.AsyncClient(transport=httpx.MockTransport(unexpected_http)) as client:
        result = await posting_service.get_or_fetch_posting(
            posting_sessions, URL, client=client, now=NOW + timedelta(days=1)
        )

    assert result.id == previous.id
    assert await _snapshot(posting_sessions, previous.id) == before
