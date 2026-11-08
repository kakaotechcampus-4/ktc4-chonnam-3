"""Google Cloud TTS REST 어댑터. 키·음성 ID는 브라우저에 전달하지 않는다."""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import math
from collections.abc import Awaitable, Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal, Protocol

import httpx
from anyio import CancelScope
from pydantic import SecretStr


class TtsError(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class TTSSettings:
    voice_map: Mapping[str, str]
    api_key: SecretStr | None = None
    access_token: SecretStr | None = None
    language_code: str = "ko-KR"
    timeout_seconds: float = 20
    max_text_bytes: int = 4500
    max_audio_bytes: int = 2097152
    cache_ttl_seconds: int = 3600
    provider: str = "google_cloud"
    monthly_character_limit: int | None = None
    budget_project: str | None = None

    def __post_init__(self) -> None:
        if self.provider != "google_cloud":
            raise ValueError("Unsupported TTS provider")
        credentials = (self.api_key, self.access_token)
        if not any(value is not None and value.get_secret_value().strip() for value in credentials):
            raise ValueError("TTS credentials are required")
        if set(self.voice_map) != {"tech_lead", "domain_lead", "hr_manager"} or any(
            not isinstance(v, str) or not v.strip() for v in self.voice_map.values()
        ):
            raise ValueError("TTS requires a voice for every persona")
        if (
            not self.language_code.strip()
            or not math.isfinite(self.timeout_seconds)
            or self.timeout_seconds <= 0
        ):
            raise ValueError("Invalid TTS language or timeout")
        if any(
            type(x) is not int or x <= 0
            for x in (self.max_text_bytes, self.max_audio_bytes, self.cache_ttl_seconds)
        ):
            raise ValueError("Invalid TTS limits")
        object.__setattr__(self, "voice_map", MappingProxyType(dict(self.voice_map)))
        if self.monthly_character_limit is not None and (
            type(self.monthly_character_limit) is not int
            or not 0 < self.monthly_character_limit <= 1000000
        ):
            raise ValueError("Invalid free TTS character allowance")


@dataclass(frozen=True)
class SpeechAudio:
    data: bytes
    mime_type: str
    voice_id: str
    provider: str


class SpeechSynthesizer(Protocol):
    async def synthesize(self, text: str, persona: str) -> SpeechAudio: ...


@dataclass(frozen=True)
class CharacterReservation:
    token: str
    characters: int
    budget_key: str


class CharacterBudget(Protocol):
    async def reserve(self, text: str) -> CharacterReservation: ...
    async def settle(
        self,
        reservation: CharacterReservation,
        outcome: Literal["success", "uncertain", "rejected"],
    ) -> None: ...


def validate_free_request(settings: TTSSettings, text: str, persona: str) -> str:
    voice = settings.voice_map.get(persona)
    if voice is None:
        raise TtsError("unknown_persona")
    if not isinstance(text, str) or not text.strip():
        raise TtsError("empty_text")
    try:
        size = len(text.encode("utf-8"))
    except UnicodeError:
        raise TtsError("invalid_text") from None
    if size > settings.max_text_bytes:
        raise TtsError("text_too_large")
    if settings.language_code != "ko-KR" or not voice.startswith("ko-KR-Chirp3-HD-"):
        raise TtsError("unsupported_free_voice")
    if settings.monthly_character_limit is None or not settings.budget_project:
        raise TtsError("budget_unconfigured")
    return voice


async def _budgeted(
    budget: CharacterBudget, text: str, operation: Callable[[], Awaitable[SpeechAudio]]
) -> SpeechAudio:
    receipt = await budget.reserve(text)
    try:
        result = await operation()
    except BaseException as exc:
        # 전송 시도 후에는 요금 여부를 알 수 없어 예약을 환불하지 않는다.
        outcome: Literal["uncertain", "rejected"] = (
            "rejected"
            if isinstance(exc, TtsError) and exc.reason == "unauthorized"
            else "uncertain"
        )
        with CancelScope(shield=True), suppress(TtsError):
            await budget.settle(receipt, outcome)
        raise
    await budget.settle(receipt, "success")
    return result


class BudgetedSpeechSynthesizer:
    """주입한 합성기도 같은 예약 경계를 통과시킨다. 캐시 hit에서는 호출하지 않는다."""

    def __init__(
        self, synthesizer: SpeechSynthesizer, settings: TTSSettings, budget: CharacterBudget
    ):
        self.synthesizer, self.settings, self.budget = synthesizer, settings, budget

    async def synthesize(self, text: str, persona: str) -> SpeechAudio:
        validate_free_request(self.settings, text, persona)
        return await _budgeted(
            self.budget, text, lambda: self.synthesizer.synthesize(text, persona)
        )


class GoogleTTSClient:
    def __init__(
        self,
        settings: TTSSettings,
        transport: httpx.AsyncBaseTransport | None = None,
        *,
        budget: CharacterBudget | None = None,
    ) -> None:
        self.settings, self.transport = settings, transport
        self.budget = budget

    async def synthesize(self, text: str, persona: str) -> SpeechAudio:
        voice = validate_free_request(self.settings, text, persona)
        if self.budget is None:
            raise TtsError("budget_unavailable")
        return await _budgeted(self.budget, text, lambda: self._synthesize(text, voice))

    async def _synthesize(self, text: str, voice: str) -> SpeechAudio:
        headers = {}
        if self.settings.access_token is not None:
            headers["Authorization"] = "Bearer " + self.settings.access_token.get_secret_value()
            # 사용자 OAuth의 실제 quota 프로젝트를 무료 문자 예산의 프로젝트와 맞춘다.
            if self.settings.budget_project:
                headers["X-Goog-User-Project"] = self.settings.budget_project
        elif self.settings.api_key is not None:
            # API 키를 query string에 넣으면 HTTP 접근 로그에 남으므로 공식 헤더를 사용한다.
            headers["X-Goog-Api-Key"] = self.settings.api_key.get_secret_value()
        payload = {
            "input": {"text": text},
            "voice": {"languageCode": self.settings.language_code, "name": voice},
            "audioConfig": {"audioEncoding": "MP3"},
        }
        try:
            async with asyncio.timeout(self.settings.timeout_seconds):
                async with httpx.AsyncClient(
                    timeout=self.settings.timeout_seconds,
                    transport=self.transport,
                    follow_redirects=False,
                    trust_env=False,
                ) as client:
                    async with client.stream(
                        "POST",
                        "https://texttospeech.googleapis.com/v1/text:synthesize",
                        headers=headers,
                        json=payload,
                    ) as response:
                        if response.status_code != 200:
                            status = response.status_code
                            raise TtsError(
                                "unauthorized"
                                if status in (401, 403)
                                else "rate_limited"
                                if status == 429
                                else "provider_error"
                            )
                        content = bytearray()
                        # base64와 작은 JSON 부가 정보만 허용하고 디코딩 후 다시 검사한다.
                        maximum = 4 * ((self.settings.max_audio_bytes + 2) // 3) + 1024
                        async for chunk in response.aiter_bytes():
                            content.extend(chunk)
                            if len(content) > maximum:
                                raise TtsError("audio_too_large")
                        body = json.loads(content)
        except (httpx.TimeoutException, TimeoutError):
            raise TtsError("timeout") from None
        except httpx.HTTPError:
            raise TtsError("provider_error") from None
        except (ValueError, UnicodeError):
            raise TtsError("invalid_response") from None
        encoded = body.get("audioContent") if isinstance(body, dict) else None
        if not isinstance(encoded, str) or not encoded:
            raise TtsError("invalid_response")
        try:
            audio = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error):
            raise TtsError("invalid_response") from None
        if not audio:
            raise TtsError("invalid_response")
        if len(audio) > self.settings.max_audio_bytes:
            raise TtsError("audio_too_large")
        return SpeechAudio(audio, "audio/mpeg", voice, self.settings.provider)
