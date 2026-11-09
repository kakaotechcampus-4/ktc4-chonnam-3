"""작은 조각이 계속 도착해도 전사 응답 전체의 시간·바이트 예산을 지킨다."""

import asyncio

import httpx
import pytest

from app.core.config import STTSettings
from app.integrations.stt.client import MlapiSttClient, SttError, SttFailureCause


class Chunks(httpx.AsyncByteStream):
    def __init__(self, parts, delay=0):
        self.parts, self.delay = parts, delay
        self.closed = False

    async def __aiter__(self):
        for part in self.parts:
            await asyncio.sleep(self.delay)
            yield part

    async def aclose(self):
        self.closed = True


def client(stream, **changes):
    settings = STTSettings.model_validate(
        {
            "stt_provider": "mlapi",
            "stt_base_url": "https://stt.example.test",
            "stt_api_key": "test-only",
            "stt_model": "whisper-test",
            "stt_language": "korean",
            "stt_timeout_seconds": 1,
            "stt_max_response_bytes": 64,
            "stt_max_audio_bytes": 1024,
            "stt_min_audio_bytes": 0,
            "stt_hallucination_phrases": (),
            "stt_hallucination_max_seconds": 1,
            **changes,
        }
    )
    return MlapiSttClient(
        settings, transport=httpx.MockTransport(lambda _: httpx.Response(200, stream=stream))
    )


async def test_response_byte_limit_is_enforced_and_stream_closed():
    stream = Chunks([b'{"text":"', b"a" * 80, b'"}'])
    with pytest.raises(SttError) as exc:
        await client(stream).transcribe(b"audio", "audio/webm")
    assert exc.value.cause is SttFailureCause.INVALID_RESPONSE
    assert stream.closed


async def test_total_deadline_limits_slow_chunked_response():
    stream = Chunks([b'{"text":', b'"hello"', b"}"], delay=0.03)
    with pytest.raises(SttError) as exc:
        await client(stream, stt_timeout_seconds=0.05).transcribe(b"audio", "audio/webm")
    assert exc.value.cause is SttFailureCause.TIMEOUT
    assert stream.closed


async def test_bounded_chunked_json_keeps_existing_transcript_semantics():
    stream = Chunks([b'{"text":', b'" hello "', b"}"])
    assert await client(stream).transcribe(b"audio", "audio/webm") == "hello"
    assert stream.closed
