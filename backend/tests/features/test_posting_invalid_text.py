"""외부 공고의 NUL을 DB 오류 대신 수집 실패로 기록한다."""

from copy import deepcopy
from datetime import timedelta

import httpx
import pytest
from sqlalchemy import select

from app.db.models import JobPosting
from app.features.analysis.posting_service import fetch_posting, get_or_fetch_posting
from app.integrations.jd.base import PostingInvalidResponseError, UnsupportedSiteError
from tests.features.test_postings import NOW, PAYLOAD, URL, _fetch, _requirements
from tests.features.test_postings import posting_sessions as posting_sessions


@pytest.mark.parametrize(
    "field",
    [
        "position",
        "intro",
        "requirements",
        "preferred_points",
        "main_tasks",
        "name",
        "industry_name",
        "skill_tags",
    ],
)
async def test_nul_in_source_is_recorded_without_persisting_invalid_text(posting_sessions, field):
    payload = deepcopy(PAYLOAD)
    if field in {"name", "industry_name"}:
        payload["job"]["company"][field] = "원문\x00"
    elif field == "skill_tags":
        payload["job"][field] = [{"text": "Py\x00thon"}]
    else:
        payload["job"]["detail"][field] = "원문\x00"
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    ) as client:
        with pytest.raises(PostingInvalidResponseError):
            await fetch_posting(posting_sessions, URL, client=client, now=NOW)
    async with posting_sessions() as db:
        failed = (await db.scalars(select(JobPosting))).one()
        assert failed.parse_status == "failed" and failed.parse_error_code == "jd_fetch_failed"
        assert failed.raw_payload is None and failed.position is None
        assert failed.company_name is None and failed.skill_tags == []
        assert failed.fetched_at is None
    assert await _requirements(posting_sessions, failed.id) == []


async def test_nul_without_requirements_keeps_prior_success_and_records_fetch_failure(
    posting_sessions,
):
    previous = await _fetch(posting_sessions)
    requirements = await _requirements(posting_sessions, previous.id)
    payload = {"job": {"detail": {"position": "내용만 있음\x00"}}}
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    ) as client:
        with pytest.raises(PostingInvalidResponseError):
            await get_or_fetch_posting(
                posting_sessions, URL, client=client, now=NOW + timedelta(days=8)
            )
    async with posting_sessions() as db:
        original = await db.get(JobPosting, previous.id)
        assert original.parse_status == "succeeded"
        assert original.raw_payload == previous.raw_payload and original.fetched_at == NOW
        failed = (
            await db.scalars(select(JobPosting).where(JobPosting.parse_status == "failed"))
        ).one()
        assert failed.parse_error_code == "jd_fetch_failed" and failed.raw_payload is None
    assert [r.id for r in await _requirements(posting_sessions, previous.id)] == [
        r.id for r in requirements
    ]


async def test_literal_unicode_escape_is_preserved_as_ordinary_text(posting_sessions):
    payload = deepcopy(PAYLOAD)
    payload["job"]["detail"]["requirements"] = [r"문자 그대로 \u0000 설명"]
    saved = await _fetch(posting_sessions, payload=payload)
    assert saved.raw_payload["requirements"] == [r"문자 그대로 \u0000 설명"]
    assert (await _requirements(posting_sessions, saved.id))[0].text == r"문자 그대로 \u0000 설명"


@pytest.mark.parametrize("url", ["\x00" + URL, URL + "?track=\x00", URL + "#\x00"])
async def test_nul_in_raw_url_is_rejected_before_http_or_storage(posting_sessions, url):
    def unexpected_http(request):
        pytest.fail("NUL이 포함된 입력 URL은 수집 전에 거절해야 한다")

    async with httpx.AsyncClient(transport=httpx.MockTransport(unexpected_http)) as client:
        with pytest.raises(UnsupportedSiteError):
            await fetch_posting(posting_sessions, url, client=client, now=NOW)
    async with posting_sessions() as db:
        assert list(await db.scalars(select(JobPosting))) == []
