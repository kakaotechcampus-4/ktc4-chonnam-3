"""실제 HTTP 전송의 전체 기한과 실패한 이미지의 공유 바이트 예산을 검증한다."""

import asyncio
import time
from contextlib import asynccontextmanager

import httpx
import pytest

from app.integrations.jd.images import _image, _ImageError
from tests.integrations.test_jd_image_collection import PNG, URL, Vision, collect


@asynccontextmanager
async def image_wire(reply):
    tasks, paths = [], []

    async def serve(reader, writer):
        tasks.append(asyncio.current_task())
        try:
            request = await reader.readuntil(b"\r\n\r\n")
            path = request.split(b" ")[1].decode()
            paths.append(path)
            await reply(path, writer)
        except (ConnectionError, asyncio.IncompleteReadError):
            pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except ConnectionError:
                pass

    server = await asyncio.start_server(serve, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]

    class ToLoopback(httpx.AsyncBaseTransport):
        def __init__(self):
            self.wire = httpx.AsyncHTTPTransport(trust_env=False)

        async def handle_async_request(self, request):
            assert request.url.host == "static.wanted.co.kr"
            mapped = httpx.Request(
                request.method,
                f"http://127.0.0.1:{port}{request.url.raw_path.decode()}",
                headers=request.headers,
                extensions=request.extensions,
            )
            return await self.wire.handle_async_request(mapped)

        async def aclose(self):
            await self.wire.aclose()

    try:
        async with httpx.AsyncClient(transport=ToLoopback(), trust_env=False) as http:
            yield http, paths
    finally:
        server.close()
        await server.wait_closed()
        await asyncio.gather(*tasks, return_exceptions=True)


def headers(writer, size):
    writer.write(
        b"HTTP/1.1 200 OK\r\nContent-Type: image/png\r\nConnection: close\r\n"
        + f"Content-Length: {size}\r\n\r\n".encode()
    )


async def test_real_wire_trickle_times_out_and_next_image_is_transcribed():
    async def reply(path, writer):
        if path == "/slow.png":
            headers(writer, len(PNG) + 10)
            for chunk in [PNG, *([b"x"] * 10)]:
                await asyncio.sleep(0.02)
                writer.write(chunk)
                await writer.drain()
        else:
            headers(writer, len(PNG))
            writer.write(PNG)
            await writer.drain()

    vision = Vision()
    async with image_wire(reply) as (http, paths):
        started = time.monotonic()
        result = await collect(
            [URL.replace("jd.png", "slow.png"), URL],
            http,
            vision,
            jd_image_timeout_seconds=0.06,
            jd_image_total_timeout_seconds=0.5,
        )
        elapsed = time.monotonic() - started
    assert paths == ["/slow.png", "/jd.png"]
    assert elapsed < 0.18
    assert vision.calls == 1 and result.source_blocks[0]["block_id"] == "I1-P1-E0"
    assert "image_fetch_failed" in result.source_limitations
    assert "image_collection_timeout" not in result.source_limitations


async def test_redirect_and_download_share_one_absolute_deadline():
    async def reply(path, writer):
        await asyncio.sleep(0.15)
        if path == "/jd.png":
            writer.write(
                b"HTTP/1.1 302 Found\r\nLocation: /next.png\r\n"
                b"Content-Length: 0\r\nConnection: close\r\n\r\n"
            )
        else:
            headers(writer, len(PNG))
            writer.write(PNG)
        await writer.drain()

    async with image_wire(reply) as (http, paths):
        with pytest.raises(_ImageError, match="image_fetch_failed"):
            await _image(http, URL, 1024, 0.25)
    assert paths == ["/jd.png", "/next.png"]


class PartialStream(httpx.AsyncByteStream):
    def __init__(self, mode):
        self.mode, self.closed = mode, False

    async def __aiter__(self):
        yield PNG
        if self.mode == "failure":
            raise httpx.ReadError("fixture")
        await asyncio.Event().wait()

    async def aclose(self):
        self.closed = True


@pytest.mark.parametrize("mode", ["timeout", "failure"])
async def test_consumed_partial_chunks_are_charged_once_and_response_is_closed(mode):
    partial = PartialStream(mode)

    def reply(request):
        if request.url.path == "/jd.png":
            return httpx.Response(200, headers={"content-type": "image/png"}, stream=partial)
        return httpx.Response(200, headers={"content-type": "image/png"}, content=PNG)

    vision = Vision()
    async with httpx.AsyncClient(transport=httpx.MockTransport(reply)) as http:
        result = await collect(
            [URL, URL.replace("jd.png", "next.png")],
            http,
            vision,
            jd_max_total_image_bytes=len(PNG) * 2,
            jd_image_timeout_seconds=0.02,
            jd_image_total_timeout_seconds=0.1,
        )
    assert partial.closed and vision.calls == 0
    assert "image_fetch_failed" in result.source_limitations
    assert "image_byte_budget" in result.source_limitations
    assert "image_collection_timeout" not in result.source_limitations
    assert result.source_metadata["image_processing"]["read_bytes"] == len(PNG)


async def test_collection_timeout_charges_partial_chunks_and_closes_stream():
    partial = PartialStream("timeout")
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, headers={"content-type": "image/png"}, stream=partial
            )
        )
    ) as http:
        result = await collect(
            [URL],
            http,
            Vision(),
            jd_image_timeout_seconds=1,
            jd_image_total_timeout_seconds=0.02,
        )
    assert partial.closed
    assert "image_collection_timeout" in result.source_limitations
    assert result.source_metadata["image_processing"]["read_bytes"] == len(PNG)


async def test_failed_and_successful_images_are_each_charged_once():
    bad = b"invalid!"
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                headers={"content-type": "image/png"},
                content=bad if request.url.path == "/jd.png" else PNG,
            )
        )
    ) as http:
        vision = Vision()
        result = await collect(
            [URL, URL.replace("jd.png", "next.png")],
            http,
            vision,
            jd_max_total_image_bytes=len(bad) + len(PNG) + 1,
        )
    assert vision.calls == 1
    assert "image_format_unsupported" in result.source_limitations
    assert result.source_metadata["image_processing"]["read_bytes"] == len(bad) + len(PNG)
