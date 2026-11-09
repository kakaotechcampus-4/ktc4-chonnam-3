"""같은 Wanted URL의 이미지 전사부터 JD 저장·추천 입력까지 실제 DB로 연결한다."""

import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select

from app.core.config import Settings
from app.db.models import JdRequirement, PromptVersion
from app.features.analysis.pipeline.steps.match_score import match_technologies
from app.features.analysis.posting_domain import _input
from app.features.analysis.posting_service import get_or_fetch_posting
from app.integrations.vision.elice import VisionBlock, VisionResult
from tests.agents.test_director_prepare import response

URL = "https://www.wanted.co.kr/wd/123"
IMAGE = "https://static.wanted.co.kr/jd.png"
PNG = b"\x89PNG\r\n\x1a\nx"


class Vision:
    def __init__(self, settings):
        self.settings, self.calls = settings, 0

    async def extract(self, *args, **kwargs):
        self.calls += 1
        return VisionResult(
            f"job-{self.calls}",
            (
                VisionBlock(
                    1,
                    0,
                    "text",
                    "우대사항\nPython 경험",
                    "사용하면 안 되는 생성 설명",
                    [0, 0, 5, 5],
                ),
            ),
            1,
            {"pages": []},
        )


def config():
    return Settings(
        _env_file=None,
        openai_api_key="fixture",
        llm_default_model="fixture",
        llm_timeout_seconds=2,
        llm_max_output_tokens=2048,
        llm_max_input_bytes=32768,
        llm_max_response_bytes=65536,
        vision_base_url="https://vision.example",
        vision_api_key="fixture",
    )


async def test_image_url_uses_source_bound_jd_then_cache_domain_and_matching(
    session_factory, monkeypatch
):
    async with session_factory.begin() as db:
        db.add(
            PromptVersion(
                task_name="jd_extract_image",
                version="jd_extract_image_v1",
                model="fixture",
                template="fixture image extraction",
                is_active=True,
            )
        )
    vision = Vision(config().require_vision())
    monkeypatch.setattr("app.integrations.jd.images.EliceVisionClient", lambda settings: vision)
    calls = []

    def handle(request):
        calls.append(request)
        if request.url.host == "www.wanted.co.kr":
            return httpx.Response(
                200, json={"job": {"detail": {"position": "개발자", "image_urls": [IMAGE]}}}
            )
        if request.url.host == "static.wanted.co.kr":
            return httpx.Response(200, content=PNG, headers={"Content-Type": "image/png"})
        body = json.loads(request.content)
        payload = json.loads(body["input"][0]["content"][0]["text"])
        assert all("생성 설명" not in block["text"] for block in payload["blocks"])
        return response(
            {
                "requirements": [
                    {
                        "category": "preferred",
                        "text": "Python 경험",
                        "tech_tags": ["Python"],
                        "source_ids": ["I0-P1-E0"],
                    }
                ],
                "limitations": [],
            }
        )

    now = datetime.now(UTC)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        posting = await get_or_fetch_posting(
            session_factory, URL, client=http, settings=config(), now=now
        )
        same = await get_or_fetch_posting(
            session_factory, URL, client=http, settings=config(), now=now + timedelta(days=1)
        )
        assert same.id == posting.id and vision.calls == 1 and len(calls) == 3
        rechecked = await get_or_fetch_posting(
            session_factory, URL, client=http, settings=config(), now=now + timedelta(days=8)
        )
        assert rechecked.id == posting.id and vision.calls == 2
    async with session_factory() as db:
        rows = list(
            (
                await db.scalars(
                    select(JdRequirement).where(JdRequirement.job_posting_id == posting.id)
                )
            ).all()
        )
    assert len(rows) == 1 and rows[0].category == "preferred"
    assert rows[0].source_refs[0]["block_id"] == "I0-P1-E0"
    snapshot = posting.raw_payload
    assert rows[0].source_refs[0]["text_hash"] == snapshot["source_blocks"][0]["text_hash"]
    assert snapshot["source_blocks"][0]["coordinate"] == [0, 0, 5, 5]
    assert _input(snapshot).preferred_points == ("Python 경험",)
    assert posting.skill_tags == ["Python"]
    assert match_technologies(posting.skill_tags, ["Python"], rows).requirement_ids == (rows[0].id,)
    assert snapshot["_image_extraction"]["attempts"]


async def test_mixed_posting_keeps_structured_requirements_when_vision_unavailable(session_factory):
    payload = {"job": {"detail": {"requirements": ["Python 경험"], "image_urls": [IMAGE]}}}
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    ) as http:
        posting = await get_or_fetch_posting(
            session_factory, URL, client=http, settings=Settings(_env_file=None)
        )
    async with session_factory() as db:
        rows = list(
            (
                await db.scalars(
                    select(JdRequirement).where(JdRequirement.job_posting_id == posting.id)
                )
            ).all()
        )
    assert rows[0].category == "required" and posting.parse_status == "succeeded"
    assert "jd_vision_not_configured" in posting.raw_payload["_image_extraction"]["limitations"]


async def test_image_cannot_change_the_category_of_an_existing_structured_requirement(
    session_factory, monkeypatch
):
    async with session_factory.begin() as db:
        db.add(
            PromptVersion(
                task_name="jd_extract_image",
                version="jd_extract_image_v1",
                model="fixture",
                template="fixture",
                is_active=True,
            )
        )
    monkeypatch.setattr("app.integrations.jd.images.EliceVisionClient", Vision)

    def handle(request):
        if request.url.host == "www.wanted.co.kr":
            return httpx.Response(
                200,
                json={
                    "job": {
                        "detail": {"requirements": ["Python 경험"], "image_urls": [IMAGE]},
                        "skill_tags": [{"text": "Python"}],
                    }
                },
            )
        if request.url.host == "static.wanted.co.kr":
            return httpx.Response(200, content=PNG, headers={"Content-Type": "image/png"})
        return response(
            {
                "requirements": [
                    {
                        "category": "preferred",
                        "text": "Python 경험",
                        "tech_tags": ["Python"],
                        "source_ids": ["I0-P1-E0"],
                    }
                ],
                "limitations": [],
            }
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        posting = await get_or_fetch_posting(session_factory, URL, client=http, settings=config())
    async with session_factory() as db:
        rows = list(
            (
                await db.scalars(
                    select(JdRequirement).where(JdRequirement.job_posting_id == posting.id)
                )
            ).all()
        )
    assert [(item.category, item.text) for item in rows] == [("required", "Python 경험")]
    assert (
        "image_structured_category_conflict"
        in posting.raw_payload["_image_extraction"]["limitations"]
    )
    assert posting.raw_payload["_image_extraction"]["source_conflicts"]


async def test_unknown_image_source_never_becomes_a_requirement_row(session_factory, monkeypatch):
    from app.db.models import JobPosting
    from app.llm_tasks.jd_extract import JdExtractionError

    async with session_factory.begin() as db:
        db.add(
            PromptVersion(
                task_name="jd_extract_image",
                version="jd_extract_image_v1",
                model="fixture",
                template="fixture",
                is_active=True,
            )
        )
    monkeypatch.setattr("app.integrations.jd.images.EliceVisionClient", Vision)

    def handle(request):
        if request.url.host == "www.wanted.co.kr":
            return httpx.Response(200, json={"job": {"detail": {"image_urls": [IMAGE]}}})
        if request.url.host == "static.wanted.co.kr":
            return httpx.Response(200, content=PNG, headers={"Content-Type": "image/png"})
        return response(
            {
                "requirements": [
                    {
                        "category": "preferred",
                        "text": "Python 경험",
                        "tech_tags": ["Python"],
                        "source_ids": ["not-read"],
                    }
                ],
                "limitations": [],
            }
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        with pytest.raises(JdExtractionError):
            await get_or_fetch_posting(session_factory, URL, client=http, settings=config())
    async with session_factory() as db:
        posting = await db.scalar(select(JobPosting))
        assert list((await db.scalars(select(JdRequirement))).all()) == []
    assert posting.parse_status == "failed" and posting.raw_payload["source_blocks"]
    metadata = posting.raw_payload["_image_extraction"]
    assert metadata["rejected"] and len(metadata["attempts"]) == 1
