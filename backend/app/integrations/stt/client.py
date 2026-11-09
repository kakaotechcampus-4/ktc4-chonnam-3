"""MLAPI Whisper 전사 어댑터. 오디오 bytes와 mime을 받아 전사 텍스트만 돌려준다.

실측 기준: 서버는 파일 내용을 보고 형식을 판별하므로 mime·파일명은 전사 결과와 무관하다.
오류 본문·응답 원문·키는 예외와 로그에 싣지 않는다. 재시도는 없다(같은 턴 재답변이 복구 경로).
"""

from __future__ import annotations

import asyncio
import logging
from enum import StrEnum

import httpx

from app.core.config import STTSettings

logger = logging.getLogger(__name__)

TRANSCRIPTIONS_PATH = "/v1/audio/transcriptions"


class SttFailureCause(StrEnum):
    """WS `error.details.cause`로 옮길 수 있는 실패 구분."""

    UNAUTHORIZED = "unauthorized"  # 401·403: 키 문제라 사용자가 다시 말해도 복구되지 않는다.
    INVALID_AUDIO = "invalid_audio"  # 400 또는 빈 오디오: 서버가 오디오를 해석하지 못함
    AUDIO_TOO_LARGE = "audio_too_large"
    PROVIDER_ERROR = "provider_error"  # 그 외 HTTP 오류·네트워크 오류
    TIMEOUT = "timeout"
    INVALID_RESPONSE = "invalid_response"  # JSON 아님·text 누락
    EMPTY_TRANSCRIPT = "empty_transcript"


class SttError(Exception):
    """STT 실패. 메시지는 고정 문구이며 공급자 원문을 포함하지 않는다."""

    def __init__(self, cause: SttFailureCause) -> None:
        self.cause = cause
        super().__init__(f"stt failed: {cause.value}")


_EXTENSION_BY_MIME = {
    "audio/webm": "webm",
    "audio/mp4": "mp4",
    "audio/ogg": "ogg",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/mpeg": "mp3",
}


# webm/opus 기준 초당 약 4KB(0007). usage.seconds가 없을 때만 길이 추정에 쓴다.
ESTIMATED_BYTES_PER_SECOND = 4096


def _normalize(text: str) -> str:
    """공백·문장부호 차이를 무시하고 비교한다."""
    return "".join(char for char in text if char.isalnum()).lower()


def _base_mime(mime: str) -> str:
    return mime.split(";", 1)[0].strip().lower() or "application/octet-stream"


class MlapiSttClient:
    """`transcribe(audio, mime)` 한 가지 책임. transport는 테스트에서 mock으로 바꾼다."""

    def __init__(
        self, settings: STTSettings, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self._settings = settings
        self._transport = transport

    async def transcribe(self, audio: bytes, mime: str) -> str:
        self._validate_audio(audio)
        base_mime = _base_mime(mime)
        filename = f"answer.{_EXTENSION_BY_MIME.get(base_mime, 'bin')}"
        settings = self._settings
        try:
            # HTTPX의 조각별 read timeout과 별도로 전체 업로드·수신 시간을 제한한다.
            async with asyncio.timeout(settings.stt_timeout_seconds):
                async with httpx.AsyncClient(
                    timeout=settings.stt_timeout_seconds, transport=self._transport
                ) as client:
                    async with client.stream(
                        "POST",
                        f"{settings.stt_base_url}{TRANSCRIPTIONS_PATH}",
                        headers={
                            "Authorization": f"Bearer {settings.stt_api_key.get_secret_value()}"
                        },
                        data={
                            "model": settings.stt_model,
                            "language": settings.stt_language,
                            "return_timestamps": "false",
                        },
                        files={"file": (filename, audio, base_mime)},
                    ) as streamed:
                        content = bytearray()
                        # 오류 본문은 필요하지 않으며 큰 오류 페이지도 메모리에 모으지 않는다.
                        if streamed.status_code == 200:
                            async for chunk in streamed.aiter_bytes():
                                if len(content) + len(chunk) > settings.stt_max_response_bytes:
                                    raise self._fail(SttFailureCause.INVALID_RESPONSE)
                                content.extend(chunk)
                        response = httpx.Response(streamed.status_code, content=bytes(content))
        except (TimeoutError, httpx.TimeoutException):
            raise self._fail(SttFailureCause.TIMEOUT) from None
        except httpx.HTTPError:
            raise self._fail(SttFailureCause.PROVIDER_ERROR) from None
        return self._parse(response, len(audio))

    def _validate_audio(self, audio: bytes) -> None:
        """호출 전 오디오 검사. 지나치게 짧거나 상한을 넘으면 전송하지 않는다."""
        if len(audio) < max(1, self._settings.stt_min_audio_bytes):
            raise self._fail(SttFailureCause.EMPTY_TRANSCRIPT)
        if len(audio) > self._settings.stt_max_audio_bytes:
            raise self._fail(SttFailureCause.AUDIO_TOO_LARGE)

    def _parse(self, response: httpx.Response, audio_bytes: int) -> str:
        status = response.status_code
        if status in (401, 403):
            raise self._fail(SttFailureCause.UNAUTHORIZED)
        if status == 400:
            raise self._fail(SttFailureCause.INVALID_AUDIO)
        if status != 200:
            raise self._fail(SttFailureCause.PROVIDER_ERROR)
        try:
            body = response.json()
        except ValueError:
            raise self._fail(SttFailureCause.INVALID_RESPONSE) from None
        text = body.get("text") if isinstance(body, dict) else None
        if not isinstance(text, str):
            raise self._fail(SttFailureCause.INVALID_RESPONSE)
        text = text.strip()
        if not text or self._is_silence_hallucination(text, body, audio_bytes):
            raise self._fail(SttFailureCause.EMPTY_TRANSCRIPT)
        return text

    def _is_silence_hallucination(self, text: str, body: object, audio_bytes: int) -> bool:
        """무음에도 200과 함께 오는 "감사합니다." 같은 환각을 빈 전사로 본다.

        전사 전체가 알려진 문구와 같고 오디오가 짧을 때만 걸러, 긴 답변 속 같은 문구는 두지 않는다.
        길이는 응답의 usage.seconds를 쓰고 없으면 크기로 추정한다.
        """
        phrases = {_normalize(phrase) for phrase in self._settings.stt_hallucination_phrases}
        if _normalize(text) not in phrases - {""}:
            return False
        usage = body.get("usage") if isinstance(body, dict) else None
        reported = usage.get("seconds") if isinstance(usage, dict) else None
        seconds = (
            float(reported)
            if isinstance(reported, (int, float))
            and not isinstance(reported, bool)
            and reported >= 0
            else audio_bytes / ESTIMATED_BYTES_PER_SECOND
        )
        return seconds <= self._settings.stt_hallucination_max_seconds

    def _fail(self, cause: SttFailureCause) -> SttError:
        logger.warning("stt_failed", extra={"cause": cause.value})
        return SttError(cause)
