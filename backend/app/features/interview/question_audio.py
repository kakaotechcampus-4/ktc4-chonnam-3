"""확정 질문의 음성 캐시. 면접 소유권 검사는 캐시 접근 전후에 호출자가 수행한다."""

from __future__ import annotations

import asyncio
import hashlib
import json
import secrets
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass
from math import ceil
from typing import cast
from uuid import UUID

from anyio import CancelScope
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.models import InterviewSession, InterviewTurn
from app.integrations.tts.google import SpeechAudio, SpeechSynthesizer, TtsError, TTSSettings
from app.shared.enums import Reason

_RELEASE = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
return redis.call('DEL', KEYS[1]) end
return 0
"""


@dataclass(frozen=True)
class AudioQuestion:
    interview_id: UUID
    turn_no: int
    turn_id: UUID
    text: str
    persona: str


async def load_question(
    db: AsyncSession, *, user_id: UUID, interview_id: UUID, turn_no: int
) -> AudioQuestion:
    interview = await db.get(InterviewSession, interview_id)
    if interview is None or interview.user_id != user_id:
        raise AppError(Reason.NOT_FOUND)
    turn = await db.scalar(
        select(InterviewTurn).where(
            InterviewTurn.interview_session_id == interview_id, InterviewTurn.turn_no == turn_no
        )
    )
    if turn is None or not turn.question_text.strip():
        raise AppError(Reason.NOT_FOUND)
    return AudioQuestion(interview_id, turn_no, turn.id, turn.question_text, turn.persona)


def question_audio_url(api_prefix: str, interview_id: UUID, turn_no: int) -> str:
    return f"{api_prefix.rstrip('/')}/interviews/{interview_id}/turns/{turn_no}/question-audio"


class QuestionAudioService:
    def __init__(self, redis: Redis, synthesizer: SpeechSynthesizer, settings: TTSSettings) -> None:
        self.redis, self.synthesizer, self.settings = redis, synthesizer, settings

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
            ],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return (
            f"question-audio:{question.interview_id}:{question.turn_no}:"
            + hashlib.sha256(value.encode()).hexdigest()
        )

    async def get(
        self, question: AudioQuestion, *, check_current: Callable[[], Awaitable[bool]] | None = None
    ) -> SpeechAudio:
        key, owner = self._key(question), secrets.token_urlsafe(24)
        lock = key + ":lock"
        acquired = False
        try:
            async with asyncio.timeout(self.settings.timeout_seconds + 1):
                while True:
                    cached = await self.redis.get(key)
                    if cached is not None:
                        return self._decode(question, cached)
                    if await self.redis.get(key + ":failed") is not None:
                        raise TtsError("temporarily_unavailable")
                    acquired = bool(
                        await self.redis.set(
                            lock, owner, nx=True, ex=ceil(self.settings.timeout_seconds) + 2
                        )
                    )
                    if acquired:
                        # 최초 조회와 잠금 획득 사이에 다른 요청이 결과를 남겼을 수 있다.
                        cached = await self.redis.get(key)
                        if cached is not None:
                            return self._decode(question, cached)
                        audio = await self.synthesizer.synthesize(question.text, question.persona)
                        if (
                            not audio.data
                            or len(audio.data) > self.settings.max_audio_bytes
                            or audio.mime_type not in {"audio/mpeg", "audio/wav", "audio/ogg"}
                        ):
                            raise TtsError("invalid_response")
                        if check_current is not None and not await check_current():
                            raise TtsError("source_changed")
                        await self.redis.set(
                            key,
                            audio.mime_type.encode() + b"\n" + audio.data,
                            ex=self.settings.cache_ttl_seconds,
                        )
                        return audio
                    await asyncio.sleep(0.05)
        except TimeoutError:
            raise TtsError("timeout") from None
        except RedisError:
            raise TtsError("cache_unavailable") from None
        except TtsError:
            if acquired:
                # 실패 연타가 같은 질문을 반복 합성하지 않도록 짧은 냉각 시간을 둔다.
                with suppress(RedisError):
                    await self.redis.set(
                        key + ":failed", b"1", ex=min(30, self.settings.cache_ttl_seconds)
                    )
            raise
        finally:
            if acquired:
                with CancelScope(shield=True), suppress(RedisError):
                    execute = cast(Callable[..., Awaitable[object]], self.redis.execute_command)
                    await execute("EVAL", _RELEASE, 1, lock, owner)

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
