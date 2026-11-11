"""확정 질문의 음성 캐시. 면접 소유권 검사는 캐시 접근 전후에 호출자가 수행한다."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import secrets
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass
from math import ceil
from typing import cast
from uuid import UUID

from anyio import CancelScope
from devon_ai.contracts import AttemptMetadata, PromptSpec
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import LLMSettings, Settings
from app.core.errors import AppError
from app.db.models import InterviewSession, InterviewTurn, LLMCallRecord
from app.features.interview.question_speech import QUESTION_SPEECH_VERSION, prepare_question_speech
from app.integrations.tts.google import (
    FINALIZATION_TIMEOUT_SECONDS,
    CompletedSpeechCancelled,
    SpeechAudio,
    SpeechSynthesizer,
    TtsError,
    TTSSettings,
    complete_audio_finalization,
)
from app.integrations.tts.pronunciation import SpeechFragment
from app.llm_tasks.prompt_loader import (
    PromptConfigurationError,
    PromptNotFoundError,
    load_active_prompt,
)
from app.llm_tasks.question_pronunciation import (
    QUESTION_PRONUNCIATION_TASK,
    QUESTION_PRONUNCIATION_TIMEOUT_SECONDS,
)
from app.shared.enums import Reason

_RELEASE = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
return redis.call('DEL', KEYS[1]) end
return 0
"""
# 공급자 마감 직후 시도 기록을 반환할 시간을 짧게 확보한다.
_PRONUNCIATION_STAGE_SECONDS = QUESTION_PRONUNCIATION_TIMEOUT_SECONDS + 0.25
_PRONUNCIATION_RETRY_SECONDS = 60
logger = logging.getLogger(__name__)

type PronounceFragments = Callable[[tuple[SpeechFragment, ...]], Awaitable[tuple[str, ...] | None]]
type CheckCurrent = Callable[[], Awaitable[bool]]


@dataclass(frozen=True)
class AudioQuestion:
    interview_id: UUID
    turn_no: int
    turn_id: UUID
    text: str
    persona: str


@dataclass(frozen=True)
class SpokenQuestion:
    text: str
    retry_pronunciation: bool = False


async def load_question(
    db: AsyncSession, *, user_id: UUID, interview_id: UUID, turn_no: int
) -> AudioQuestion:
    interview = await db.get(InterviewSession, interview_id, populate_existing=True)
    if interview is None or interview.user_id != user_id:
        raise AppError(Reason.NOT_FOUND)
    # 현재 음성 면접의 미답변 질문만 유료 합성한다. 과거 면접 재생으로 예산을 소모하지 않는다.
    if (
        interview.answer_mode != "voice"
        or interview.status != "in_progress"
        or interview.current_turn != turn_no
    ):
        raise AppError(Reason.NOT_READY)
    turn = await db.scalar(
        select(InterviewTurn).where(
            InterviewTurn.interview_session_id == interview_id, InterviewTurn.turn_no == turn_no
        )
    )
    if turn is None or not turn.question_text.strip():
        raise AppError(Reason.NOT_FOUND)
    if turn.status != "asked" or turn.answer_text is not None:
        raise AppError(Reason.NOT_READY)
    return AudioQuestion(interview_id, turn_no, turn.id, turn.question_text, turn.persona)


def question_audio_url(api_prefix: str, interview_id: UUID, turn_no: int) -> str:
    return f"{api_prefix.rstrip('/')}/interviews/{interview_id}/turns/{turn_no}/question-audio"


async def load_question_pronunciation(
    db: AsyncSession, settings: Settings, *, text: str
) -> tuple[LLMSettings, PromptSpec] | None:
    if not prepare_question_speech(text).fragments:
        return None
    try:
        llm = settings.require_llm()
        model = settings.tts_pronunciation_model or llm.llm_default_model
        async with asyncio.timeout(FINALIZATION_TIMEOUT_SECONDS):
            prompt = await load_active_prompt(db, QUESTION_PRONUNCIATION_TASK)
        if prompt.model == model:
            return llm, prompt
    except (
        ValueError,
        PromptNotFoundError,
        PromptConfigurationError,
        SQLAlchemyError,
        TimeoutError,
    ):
        logger.warning("question_pronunciation_unavailable")
        return None
    finally:
        await db.rollback()
    logger.warning("question_pronunciation_model_mismatch")
    return None


async def record_question_pronunciation(
    db: AsyncSession, question: AudioQuestion, attempts: list[AttemptMetadata]
) -> None:
    if not attempts:
        return
    last = attempts[-1]
    try:
        async with asyncio.timeout(0.25), db.begin():
            db.add(
                LLMCallRecord(
                    interview_session_id=question.interview_id,
                    turn_id=question.turn_id,
                    turn_no=question.turn_no,
                    task_name=QUESTION_PRONUNCIATION_TASK,
                    attempts=[
                        {
                            "attempt": item.attempt,
                            "provider": item.provider,
                            "model": item.model,
                            "prompt_version": item.prompt_version,
                            "schema_version": item.schema_version,
                            "latency_ms": item.latency_ms,
                            "input_tokens": item.input_tokens,
                            "output_tokens": item.output_tokens,
                            "error_stage": item.error_stage,
                            "error_code": item.error_code,
                        }
                        for item in attempts
                    ],
                    failure={"stage": last.error_stage, "error_code": last.error_code}
                    if last.error_code
                    else None,
                )
            )
    except (SQLAlchemyError, TimeoutError):
        logger.warning("question_pronunciation_record_unavailable")


class QuestionAudioService:
    def __init__(
        self,
        redis: Redis,
        synthesizer: SpeechSynthesizer,
        settings: TTSSettings,
        *,
        pronounce: PronounceFragments | None = None,
        pronunciation_identity: str | None = None,
    ) -> None:
        if (pronounce is None) != (pronunciation_identity is None):
            raise ValueError("pronunciation requires a matching cache identity")
        self.redis, self.synthesizer, self.settings = redis, synthesizer, settings
        self.pronounce, self.pronunciation_identity = pronounce, pronunciation_identity

    def _key(self, question: AudioQuestion) -> str:
        voice = self.settings.voice_map.get(question.persona)
        if voice is None:
            raise TtsError("unknown_persona")
        value = json.dumps(
            [
                str(question.turn_id),
                question.text,
                question.persona,
                self.settings.provider,
                voice,
                self.settings.language_code,
                "mp3.v1",
                QUESTION_SPEECH_VERSION,
                self.pronunciation_identity,
            ],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return (
            f"question-audio:{question.interview_id}:{question.turn_no}:"
            + hashlib.sha256(value.encode()).hexdigest()
        )

    async def _cache_completed(
        self,
        key: str,
        audio: SpeechAudio,
        check_current: CheckCurrent | None,
        speech_digest: bytes,
        retry_pronunciation: bool,
    ) -> None:
        validated = False

        async def store() -> None:
            nonlocal validated
            if (
                not audio.data
                or len(audio.data) > self.settings.max_audio_bytes
                or audio.mime_type not in {"audio/mpeg", "audio/wav", "audio/ogg"}
            ):
                raise TtsError("invalid_response")
            if check_current is not None and not await check_current():
                raise TtsError("source_changed")
            validated = True
            try:
                payload = audio.mime_type.encode() + b"\n" + audio.data
                ttl = self.settings.cache_ttl_seconds
                if retry_pronunciation:
                    # 재시도 중 같은 기본 음성을 다시 유료 합성하지 않게 먼저 보관한다.
                    await self.redis.set(
                        key + ":fallback",
                        speech_digest + b"\n" + payload,
                        ex=ttl,
                        nx=True,
                    )
                    ttl = min(ttl, _PRONUNCIATION_RETRY_SECONDS)
                await self.redis.set(
                    key,
                    payload,
                    ex=ttl,
                )
            except RedisError:
                # 이미 얻은 결과는 반환한다. 새 합성의 예약·epoch 검사는 계속 fail-closed다.
                logger.warning("question_audio_cache_write_unavailable")

        try:
            await complete_audio_finalization(store)
        except TimeoutError:
            if not validated:
                raise TtsError("source_check_unavailable") from None
            logger.warning("question_audio_cache_write_timeout")

    async def _require_current(self, check_current: CheckCurrent | None) -> None:
        if check_current is None:
            return
        try:
            current = await complete_audio_finalization(check_current)
        except TimeoutError:
            raise TtsError("source_check_unavailable") from None
        if not current:
            raise TtsError("source_changed")

    async def _spoken_text(self, text: str, check_current: CheckCurrent | None) -> SpokenQuestion:
        if self.settings.language_code.casefold() != "ko-kr":
            return SpokenQuestion(text)
        prepared = prepare_question_speech(text)
        if not prepared.text.strip() or len(prepared.text.encode()) > self.settings.max_text_bytes:
            return SpokenQuestion(text)
        if self.pronounce is None or not prepared.fragments:
            return SpokenQuestion(prepared.text)

        try:
            async with asyncio.timeout(_PRONUNCIATION_STAGE_SECONDS):
                pronunciations = await self.pronounce(prepared.fragments)
        except TimeoutError:
            logger.info("question_pronunciation_timeout")
            pronunciations = None
        # 모델을 기다리는 동안 답변 제출이나 턴 전환이 일어날 수 있다.
        await self._require_current(check_current)
        if pronunciations is None or len(pronunciations) != len(prepared.fragments):
            return SpokenQuestion(prepared.text, retry_pronunciation=True)
        try:
            spoken = prepared.with_pronunciations(pronunciations)
        except ValueError:
            return SpokenQuestion(prepared.text, retry_pronunciation=True)
        if len(spoken.encode()) > self.settings.max_text_bytes:
            return SpokenQuestion(prepared.text, retry_pronunciation=True)
        return SpokenQuestion(spoken)

    async def _read_fallback(
        self, key: str, question: AudioQuestion
    ) -> tuple[bytes, SpeechAudio] | None:
        stored = await self.redis.get(key + ":fallback")
        if stored is None:
            return None
        if not isinstance(stored, bytes):
            raise TtsError("invalid_cache")
        digest, separator, audio = stored.partition(b"\n")
        if (
            not separator
            or len(digest) != 64
            or any(char not in b"0123456789abcdef" for char in digest)
        ):
            raise TtsError("invalid_cache")
        return digest, self._decode(question, audio)

    async def get(
        self, question: AudioQuestion, *, check_current: CheckCurrent | None = None
    ) -> SpeechAudio:
        key, owner = self._key(question), secrets.token_urlsafe(24)
        lock = key + ":lock"
        acquired = False
        try:
            # 공급자 대기와 정산·캐시 두 마무리 상한을 합쳐 lock이 먼저 풀리지 않게 한다.
            operation_seconds = self.settings.timeout_seconds + 2 * FINALIZATION_TIMEOUT_SECONDS
            if self.pronounce is not None:
                operation_seconds += _PRONUNCIATION_STAGE_SECONDS + FINALIZATION_TIMEOUT_SECONDS
            async with asyncio.timeout(operation_seconds + 1):
                while True:
                    cached = await self.redis.get(key)
                    if cached is not None:
                        return self._decode(question, cached)
                    if await self.redis.get(key + ":failed") is not None:
                        raise TtsError("temporarily_unavailable")
                    acquired = bool(
                        await self.redis.set(lock, owner, nx=True, ex=ceil(operation_seconds) + 2)
                    )
                    if acquired:
                        # 최초 조회와 잠금 획득 사이에 다른 요청이 결과를 남겼을 수 있다.
                        cached = await self.redis.get(key)
                        if cached is not None:
                            return self._decode(question, cached)
                        if await self.redis.get(key + ":failed") is not None:
                            raise TtsError("temporarily_unavailable")
                        await self._require_current(check_current)
                        spoken = await self._spoken_text(question.text, check_current)
                        speech_digest = hashlib.sha256(spoken.text.encode()).hexdigest().encode()
                        retry_pronunciation = spoken.retry_pronunciation
                        fallback = await self._read_fallback(key, question)
                        audio = fallback[1] if fallback and fallback[0] == speech_digest else None
                        if audio is None:
                            try:
                                audio = await self.synthesizer.synthesize(
                                    spoken.text, question.persona
                                )
                            except CompletedSpeechCancelled as exc:
                                try:
                                    await self._cache_completed(
                                        key,
                                        exc.audio,
                                        check_current,
                                        speech_digest,
                                        retry_pronunciation,
                                    )
                                finally:
                                    raise asyncio.CancelledError from None
                            except TtsError:
                                if fallback is None:
                                    raise
                                # 개선 음성을 못 만들더라도 이미 확보한 현재 질문은 재생한다.
                                speech_digest, audio = fallback
                                retry_pronunciation = True
                        await self._cache_completed(
                            key, audio, check_current, speech_digest, retry_pronunciation
                        )
                        return audio
                    await asyncio.sleep(0.05)
        except TimeoutError:
            if acquired:
                await self._cooldown(key)
            raise TtsError("timeout") from None
        except RedisError:
            raise TtsError("cache_unavailable") from None
        except TtsError as exc:
            if acquired and exc.reason != "temporarily_unavailable":
                # 실패 연타가 같은 질문을 반복 합성하지 않도록 짧은 냉각 시간을 둔다.
                await self._cooldown(key)
            raise
        finally:
            if acquired:
                with CancelScope(shield=True), suppress(RedisError):
                    with suppress(TimeoutError):
                        async with asyncio.timeout(FINALIZATION_TIMEOUT_SECONDS):
                            execute = cast(
                                Callable[..., Awaitable[object]], self.redis.execute_command
                            )
                            await execute("EVAL", _RELEASE, 1, lock, owner)

    async def _cooldown(self, key: str) -> None:
        with suppress(RedisError, TimeoutError):
            async with asyncio.timeout(FINALIZATION_TIMEOUT_SECONDS):
                await self.redis.set(
                    key + ":failed", b"1", ex=min(30, self.settings.cache_ttl_seconds)
                )

    def _decode(self, question: AudioQuestion, raw: bytes | str) -> SpeechAudio:
        if not isinstance(raw, bytes):
            raise TtsError("invalid_cache")
        mime, separator, audio = raw.partition(b"\n")
        if (
            not separator
            or mime not in {b"audio/mpeg", b"audio/wav", b"audio/ogg"}
            or not audio
            or len(audio) > self.settings.max_audio_bytes
        ):
            raise TtsError("invalid_cache")
        return SpeechAudio(
            audio,
            mime.decode("ascii"),
            self.settings.voice_map[question.persona],
            self.settings.provider,
        )
