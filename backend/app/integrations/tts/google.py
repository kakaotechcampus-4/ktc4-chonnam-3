"""Google Cloud TTS REST 어댑터. 키·음성 ID는 브라우저에 전달하지 않는다."""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import logging
import math
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal, Protocol

import httpx
from anyio import CancelScope
from anyio.lowlevel import checkpoint_if_cancelled
from pydantic import SecretStr

logger = logging.getLogger(__name__)
FINALIZATION_TIMEOUT_SECONDS = 1.0


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
        for name in ("api_key", "access_token"):
            value = getattr(self, name)
            if value is not None and not value.get_secret_value().strip():
                object.__setattr__(self, name, None)
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


class CompletedSpeechCancelled(asyncio.CancelledError):
    """이미 확보한 오디오를 캐시에 마무리한 뒤 호출자 취소를 전파한다."""

    def __init__(self, audio: SpeechAudio) -> None:
        self.audio = audio
        super().__init__("completed_speech_cancelled")


async def complete_audio_finalization[T](operation: Callable[[], Awaitable[T]]) -> T:
    """마무리는 유한 시간만 보호한다. 취소를 성공 응답으로 바꾸거나 task를 방치하지 않는다."""

    async def limited() -> T:
        async with asyncio.timeout(FINALIZATION_TIMEOUT_SECONDS):
            return await operation()

    task = asyncio.create_task(limited())
    cancelled = False
    # AnyIO 취소와 직접 Task.cancel 모두 다룬다. task는 완료까지 이 지역 참조로 유지한다.
    with CancelScope(shield=True):
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                cancelled = True
            except Exception:
                break
    try:
        result = task.result()
    finally:
        if cancelled:
            raise asyncio.CancelledError
    await checkpoint_if_cancelled()
    return result


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

    async def settle(outcome: Literal["success", "uncertain", "rejected"]) -> None:
        async def operation() -> None:
            try:
                await budget.settle(receipt, outcome)
            except TtsError:
                # 예약 used/pending은 환불하거나 재초기화하지 않는다. 원문·토큰은 기록하지 않는다.
                logger.warning("tts_budget_settlement_unavailable", extra={"outcome": outcome})

        try:
            await complete_audio_finalization(operation)
        except TimeoutError:
            logger.warning("tts_budget_settlement_timeout", extra={"outcome": outcome})

    try:
        result = await operation()
    except BaseException as exc:
        # 명시적 인증 거절만 rejected로 정산한다. 전송 결과가 불명확하면 예약을 유지한다.
        outcome: Literal["uncertain", "rejected"] = (
            "rejected"
            if isinstance(exc, TtsError) and exc.reason == "unauthorized"
            else "uncertain"
        )
        try:
            await settle(outcome)
        except asyncio.CancelledError:
            pass
        raise
    try:
        await settle("success")
    except asyncio.CancelledError:
        raise CompletedSpeechCancelled(result) from None
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
