"""Wanted 본문 이미지의 제한 수집과 Vision 전사. 생성 설명은 요구사항 원문이 아니다."""

import asyncio
import hashlib
import json
from dataclasses import replace
from urllib.parse import urljoin

import httpx

from app.core.config import Settings
from app.integrations.jd.base import PostingContent
from app.integrations.jd.body_images import WANTED_IMAGE_DOMAINS
from app.integrations.search.tavily import SearchError, checked_source_url
from app.integrations.vision.elice import EliceVisionClient, VisionError
from app.shared.storage_values import validate_storage_strings


class _ImageError(Exception):
    def __init__(self, reason: str, consumed: int = 0) -> None:
        self.reason, self.consumed = reason, consumed
        super().__init__(reason)


async def _image(
    http: httpx.AsyncClient, url: str, limit: int, request_timeout_seconds: float
) -> tuple[bytes, str]:
    if limit <= 0:
        raise _ImageError("image_byte_budget")
    body = bytearray()
    try:
        for _ in range(3):
            url = checked_source_url(url, WANTED_IMAGE_DOMAINS)
            # 주입 client의 사용자 인증·쿠키를 CDN이나 redirect 대상으로 전달하지 않는다.
            request = httpx.Request(
                "GET",
                url,
                headers={"User-Agent": "DEVON", "Accept-Encoding": "identity"},
                extensions={"timeout": httpx.Timeout(request_timeout_seconds).as_dict()},
            )
            response = await http.send(request, auth=None, stream=True, follow_redirects=False)
            try:
                if response.status_code in {301, 302, 303, 307, 308}:
                    url = checked_source_url(
                        urljoin(url, response.headers.get("Location", "")), WANTED_IMAGE_DOMAINS
                    )
                    continue
                if (
                    response.status_code != 200
                    or response.headers.get("Content-Encoding", "identity").lower() != "identity"
                ):
                    raise _ImageError("image_fetch_failed")
                declared = response.headers.get("Content-Length", "")
                if declared.isdecimal() and int(declared) >= limit:
                    raise _ImageError("image_byte_budget")
                async for chunk in response.aiter_bytes(chunk_size=limit):
                    body.extend(chunk)
                    # 경계에서 중단하므로 실패 이미지도 공유 바이트 예산 밖으로 더 읽지 않는다.
                    if len(body) >= limit:
                        raise _ImageError("image_byte_budget", len(body))
                raw = bytes(body)
                mime = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
                if not (
                    (mime == "image/png" and raw.startswith(b"\x89PNG\r\n\x1a\n"))
                    or (mime == "image/jpeg" and raw.startswith(b"\xff\xd8\xff"))
                ):
                    raise _ImageError("image_format_unsupported", len(body))
                return raw, mime
            finally:
                await response.aclose()
        raise _ImageError("image_redirect_limit")
    except SearchError:
        raise _ImageError("untrusted_body_image_url", len(body)) from None
    except httpx.HTTPError:
        raise _ImageError("image_fetch_failed", len(body)) from None


async def collect_posting_images(
    content: PostingContent,
    *,
    settings: Settings,
    http_client: httpx.AsyncClient | None = None,
    vision_client: EliceVisionClient | None = None,
) -> PostingContent:
    if not content.image_urls:
        return content
    limitations = list(content.source_limitations)
    blocks: list[dict[str, object]] = []
    records: list[dict[str, object]] = []
    try:
        vision = vision_client or EliceVisionClient(settings.require_vision())
    except ValueError:
        return replace(content, source_limitations=[*limitations, "jd_vision_not_configured"])
    urls = tuple(dict.fromkeys(content.image_urls))
    if len(urls) > settings.jd_max_images:
        limitations.append("image_count_limit")
    remaining = settings.jd_max_total_image_bytes
    chars_left = settings.documents_max_source_chars

    async def process(http: httpx.AsyncClient) -> None:
        nonlocal remaining, chars_left
        for index, url in enumerate(urls[: settings.jd_max_images]):
            if remaining <= 0:
                limitations.append("image_byte_budget")
                break
            try:
                data, mime = await _image(
                    http,
                    url,
                    min(remaining, vision.settings.max_file_bytes),
                    settings.jd_image_timeout_seconds,
                )
                remaining -= len(data)
                image_hash = hashlib.sha256(data).hexdigest()
                result = await vision.extract(
                    data,
                    mime,
                    filename=f"posting-{index}.{'png' if mime == 'image/png' else 'jpg'}",
                )
                json.dumps(result.raw_result, allow_nan=False, ensure_ascii=False).encode("utf-8")
                validate_storage_strings(result.raw_result)
                records.append(
                    {
                        "url": url,
                        "image_hash": image_hash,
                        "vision_job_id": result.job_id,
                        "vision_raw_result": result.raw_result,
                    }
                )
                limitations.extend(result.limitations)
                for block in result.blocks:
                    if not block.content or not block.content.strip():
                        limitations.append("visual_regions_not_transcribed")
                        continue
                    text = block.content.replace("\x00", "")
                    if text != block.content:
                        limitations.append("nul_characters_removed")
                    if len(text) > chars_left:
                        limitations.append("image_source_text_limit")
                        continue
                    chars_left -= len(text)
                    blocks.append(
                        {
                            "block_id": f"I{index}-P{block.page}-E{block.element_index}",
                            "text": text,
                            "text_hash": hashlib.sha256(text.encode()).hexdigest(),
                            "image_hash": image_hash,
                            "image_url": url,
                            "page": block.page,
                            "element": block.element_index,
                            "coordinate": block.coordinate,
                        }
                    )
            except _ImageError as error:
                remaining -= error.consumed
                limitations.append(error.reason)
            except VisionError as error:
                limitations.append("jd_vision_" + error.reason)
            except (ValueError, UnicodeError, RecursionError):
                limitations.append("jd_vision_metadata_invalid")

    try:
        async with asyncio.timeout(settings.jd_image_timeout_seconds):
            if http_client is not None:
                await process(http_client)
            else:
                async with httpx.AsyncClient(follow_redirects=False, trust_env=False) as http:
                    await process(http)
    except TimeoutError:
        limitations.append("image_collection_timeout")
    metadata = {
        **content.source_metadata,
        "image_processing": {
            "sources": records,
            "read_bytes": settings.jd_max_total_image_bytes - remaining,
            "status": "succeeded"
            if blocks and not limitations
            else "partial"
            if blocks
            else "failed",
        },
    }
    return replace(
        content,
        source_blocks=blocks,
        source_limitations=list(dict.fromkeys(limitations)),
        source_metadata=metadata,
    )
