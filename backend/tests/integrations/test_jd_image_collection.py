"""이미지 공고는 인증을 상속하지 않고 공유 예산과 전사/설명 경계를 지킨다."""

import asyncio
import importlib
from types import SimpleNamespace

import httpx

from app.core.config import Settings
from app.integrations.jd.base import PostingContent
from app.integrations.vision.elice import VisionBlock, VisionResult

PNG = b"\x89PNG\r\n\x1a\nx"
URL = "https://static.wanted.co.kr/jd.png"


class Vision:
    settings = SimpleNamespace(max_file_bytes=1024)

    def __init__(self):
        self.calls = 0

    async def extract(self, data, mime_type, **kwargs):
        self.calls += 1
        assert data == PNG and mime_type == "image/png"
        return VisionResult(
            "job",
            (
                VisionBlock(1, 0, "text", "자격요건\nPython 경험", None, [0, 0, 1, 1]),
                VisionBlock(1, 1, "figure", None, "생성한 도식 설명", None),
            ),
            1,
            {"pages": []},
        )


async def collect(urls, http, vision, **updates):
    name = "app.integrations.jd.images"
    assert importlib.util.find_spec(name) is not None, "이미지 원문 수집 경계가 필요하다"
    module = importlib.import_module(name)
    return await module.collect_posting_images(
        PostingContent("wanted", "https://www.wanted.co.kr/wd/1", "image", image_urls=urls),
        settings=Settings(_env_file=None, **updates),
        http_client=http,
        vision_client=vision,
    )


async def test_image_transcription_keeps_location_and_excludes_generated_description():
    def handle(request):
        assert "authorization" not in request.headers and "cookie" not in request.headers
        return httpx.Response(200, content=PNG, headers={"content-type": "image/png"})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handle),
        headers={"Authorization": "secret", "Cookie": "session=secret"},
    ) as http:
        result = await collect([URL], http, Vision())
    assert result.source_blocks[0]["text"] == "자격요건\nPython 경험"
    assert result.source_blocks[0]["page"] == 1 and result.source_blocks[0]["coordinate"] == [
        0,
        0,
        1,
        1,
    ]
    assert len(result.source_blocks) == 1
    assert "visual_regions_not_transcribed" in result.source_limitations


async def test_redirect_cannot_expand_into_private_network():
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(302, headers={"Location": "https://127.0.0.1/private"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        result = await collect([URL], http, Vision())
    assert len(calls) == 1 and result.source_blocks == []
    assert result.source_limitations


async def test_duplicate_images_share_byte_and_count_budget():
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(200, content=PNG, headers={"content-type": "image/png"})

    vision = Vision()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        result = await collect(
            [URL, URL, URL + "?second=1"],
            http,
            vision,
            jd_max_images=2,
            jd_max_total_image_bytes=12,
        )
    assert sum(request.url == URL for request in calls) == 1
    assert vision.calls == 1 and len(result.source_blocks) == 1
    assert result.source_limitations


async def test_total_collection_timeout_is_a_visible_partial_failure():
    class Waiting(Vision):
        async def extract(self, *args, **kwargs):
            await asyncio.Event().wait()

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=PNG, headers={"content-type": "image/png"})
        )
    ) as http:
        result = await collect([URL], http, Waiting(), jd_image_timeout_seconds=0.01)
    assert result.source_blocks == [] and "image_collection_timeout" in result.source_limitations
