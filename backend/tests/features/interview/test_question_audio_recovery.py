import asyncio
from uuid import uuid4

import pytest
from pydantic import SecretStr

from app.features.interview.question_audio import AudioQuestion, QuestionAudioService
from app.integrations.tts.google import (
    BudgetedSpeechSynthesizer,
    CharacterReservation,
    CompletedSpeechCancelled,
    SpeechAudio,
    TtsError,
    TTSSettings,
)


class ExpiringCache:
    def __init__(self):
        self.now = 0
        self.values = {}
        self.deadlines = {}

    async def get(self, key):
        if self.deadlines.get(key, self.now + 1) <= self.now:
            self.values.pop(key, None)
            self.deadlines.pop(key, None)
        return self.values.get(key)

    async def set(self, key, value, *, ex, nx=False):
        if nx and await self.get(key) is not None:
            return False
        self.values[key] = value.encode() if isinstance(value, str) else value
        self.deadlines[key] = self.now + ex
        return True

    async def execute_command(self, command, script, count, key, owner):
        if await self.get(key) == owner.encode():
            self.values.pop(key, None)
            self.deadlines.pop(key, None)
            return 1
        return 0


class Synthesizer:
    def __init__(self, *, cancelled=False):
        self.calls = []
        self.cancelled = cancelled

    async def synthesize(self, text, persona):
        self.calls.append(text)
        audio = SpeechAudio(b"ID3:" + text.encode(), "audio/mpeg", "voice", "google_cloud")
        if self.cancelled:
            raise CompletedSpeechCancelled(audio)
        return audio


def settings():
    return TTSSettings(
        voice_map={
            name: "ko-KR-Chirp3-HD-Charon" for name in ("tech_lead", "domain_lead", "hr_manager")
        },
        api_key=SecretStr("fixture"),
        monthly_character_limit=1000,
        budget_project="fixture",
    )


def question(text="circuit breaker의 역할을 설명해 주세요."):
    return AudioQuestion(uuid4(), 1, uuid4(), text, "tech_lead")


@pytest.mark.parametrize("failure", ["unavailable", "timeout", "invalid"])
async def test_failed_pronunciation_retries_without_resynthesizing_the_same_fallback(failure):
    cache, provider = ExpiringCache(), Synthesizer()
    attempts = []

    async def pronounce(fragments):
        attempts.append(fragments)
        if failure == "timeout":
            raise TimeoutError
        if failure == "invalid":
            return ("not-a-hangul-reading",)
        return None

    service = QuestionAudioService(
        cache, provider, settings(), pronounce=pronounce, pronunciation_identity="fixture"
    )
    source = question()
    first = await service.get(source)
    assert (await service.get(source)).data == first.data
    assert len(attempts) == len(provider.calls) == 1

    cache.now += 61
    assert (await service.get(source)).data == first.data
    assert len(attempts) == 2
    assert len(provider.calls) == 1
    assert (await service.get(source)).data == first.data
    assert len(attempts) == 2


async def test_repeated_failures_do_not_keep_the_fallback_forever():
    cache, provider = ExpiringCache(), Synthesizer()
    attempts = []

    async def pronounce(fragments):
        attempts.append(fragments)
        return None

    service = QuestionAudioService(
        cache, provider, settings(), pronounce=pronounce, pronunciation_identity="fixture"
    )
    source = question()
    await service.get(source)
    cache.now = 61
    await service.get(source)
    cache.now = settings().cache_ttl_seconds + 1
    await service.get(source)

    assert len(attempts) == 3
    assert len(provider.calls) == 2


async def test_recovered_pronunciation_is_synthesized_once_then_cached_for_the_normal_ttl():
    cache, provider = ExpiringCache(), Synthesizer()
    attempts = []

    async def pronounce(fragments):
        attempts.append(fragments)
        return None if len(attempts) == 1 else ("서킷 브레이커",)

    service = QuestionAudioService(
        cache, provider, settings(), pronounce=pronounce, pronunciation_identity="fixture"
    )
    source = question()
    before = await service.get(source)
    cache.now += 61
    recovered = await service.get(source)

    assert recovered.data != before.data
    assert provider.calls == [source.text, "서킷 브레이커의 역할을 설명해 주세요."]
    cache.now += 61
    assert (await service.get(source)).data == recovered.data
    assert len(attempts) == len(provider.calls) == 2


async def test_recovered_reading_equal_to_fallback_promotes_audio_without_new_synthesis():
    cache, provider = ExpiringCache(), Synthesizer()
    attempts = []

    async def pronounce(fragments):
        attempts.append(fragments)
        return None if len(attempts) == 1 else ("큐 유 아이 씨",)

    service = QuestionAudioService(
        cache, provider, settings(), pronounce=pronounce, pronunciation_identity="fixture"
    )
    source = question("/api/quic 경로를 설명해 주세요.")
    before = await service.get(source)
    cache.now += 61
    assert (await service.get(source)).data == before.data
    cache.now += 61
    assert (await service.get(source)).data == before.data
    assert len(attempts) == 2
    assert len(provider.calls) == 1


async def test_successful_pronunciation_does_not_retry_after_one_minute():
    cache, provider = ExpiringCache(), Synthesizer()
    attempts = []

    async def pronounce(fragments):
        attempts.append(fragments)
        return ("서킷 브레이커",)

    service = QuestionAudioService(
        cache, provider, settings(), pronounce=pronounce, pronunciation_identity="fixture"
    )
    source = question()
    before = await service.get(source)
    cache.now += 61
    assert (await service.get(source)).data == before.data
    assert len(attempts) == len(provider.calls) == 1


async def test_concurrent_retries_share_one_model_attempt_and_reuse_fallback_audio():
    cache, provider = ExpiringCache(), Synthesizer()
    attempts = []

    async def pronounce(fragments):
        attempts.append(fragments)
        await asyncio.sleep(0)
        return None

    service = QuestionAudioService(
        cache, provider, settings(), pronounce=pronounce, pronunciation_identity="fixture"
    )
    source = question()
    before = await service.get(source)
    cache.now += 61
    replay = await asyncio.gather(service.get(source), service.get(source))

    assert all(audio.data == before.data for audio in replay)
    assert len(attempts) == 2
    assert len(provider.calls) == 1


async def test_retry_does_not_return_old_audio_after_the_question_changes():
    cache, provider = ExpiringCache(), Synthesizer()
    current = True
    attempts = []

    async def pronounce(fragments):
        nonlocal current
        attempts.append(fragments)
        if len(attempts) > 1:
            current = False
        return None

    async def check_current():
        return current

    service = QuestionAudioService(
        cache, provider, settings(), pronounce=pronounce, pronunciation_identity="fixture"
    )
    source = question()
    await service.get(source, check_current=check_current)
    cache.now += 61

    with pytest.raises(TtsError, match="source_changed"):
        await service.get(source, check_current=check_current)
    assert len(attempts) == 2
    assert len(provider.calls) == 1


async def test_completed_cancelled_fallback_survives_the_retry_interval():
    cache, provider = ExpiringCache(), Synthesizer(cancelled=True)
    attempts = []

    async def pronounce(fragments):
        attempts.append(fragments)
        return None

    service = QuestionAudioService(
        cache, provider, settings(), pronounce=pronounce, pronunciation_identity="fixture"
    )
    source = question()
    with pytest.raises(asyncio.CancelledError):
        await service.get(source)
    cache.now += 61

    assert (await service.get(source)).data.startswith(b"ID3:")
    assert len(attempts) == 2
    assert len(provider.calls) == 1


async def test_retry_charges_characters_only_when_a_new_audio_is_actually_synthesized():
    class Budget:
        def __init__(self):
            self.reservations = []
            self.settled = []

        async def reserve(self, text):
            receipt = CharacterReservation(str(len(self.reservations)), len(text), "fixture")
            self.reservations.append(receipt)
            return receipt

        async def settle(self, receipt, outcome):
            self.settled.append((receipt, outcome))

    cache, provider, budget = ExpiringCache(), Synthesizer(), Budget()
    attempts = []

    async def pronounce(fragments):
        attempts.append(fragments)
        return None if len(attempts) < 3 else ("서킷 브레이커",)

    config = settings()
    service = QuestionAudioService(
        cache,
        BudgetedSpeechSynthesizer(provider, config, budget),
        config,
        pronounce=pronounce,
        pronunciation_identity="fixture",
    )
    source = question()
    await service.get(source)
    cache.now += 61
    await service.get(source)
    cache.now += 61
    await service.get(source)

    assert len(attempts) == 3
    assert len(provider.calls) == len(budget.reservations) == len(budget.settled) == 2
    assert [receipt.characters for receipt in budget.reservations] == list(map(len, provider.calls))
    assert all(outcome == "success" for _, outcome in budget.settled)
