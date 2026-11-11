from dataclasses import replace

import pytest

from app.features.interview.question_audio import QuestionAudioService
from app.integrations.tts.google import TtsError

from .test_question_audio_recovery import ExpiringCache, Synthesizer, question, settings


async def test_three_attempts_use_shared_60_and_120_second_gaps_and_fixed_expiry():
    cache, provider, attempts = ExpiringCache(), Synthesizer(), []
    source = question()

    async def pronounce(fragments):
        attempts.append(cache.now)
        return None

    async def request():
        return await QuestionAudioService(
            cache, provider, settings(), pronounce=pronounce, pronunciation_identity="fixture"
        ).get(source)

    original = await request()
    for moment, expected_count in ((61, 2), (122, 2), (182, 3), (243, 3), (3599, 3)):
        cache.now = moment
        assert (await request()).data == original.data
        assert len(attempts) == expected_count
    assert attempts == [0, 61, 182]
    assert len(provider.calls) == 1
    assert all(deadline <= 3600 for key, deadline in cache.deadlines.items() if ":lock" not in key)

    cache.now = 3601
    await request()
    assert len(attempts) == 4
    assert len(provider.calls) == 2


@pytest.mark.parametrize("output", [("not-hangul",), ("가" * 80,)])
async def test_invalid_or_oversized_model_output_has_the_same_attempt_bound(output):
    cache, provider, attempts = ExpiringCache(), Synthesizer(), []
    source = question()
    config = replace(settings(), max_text_bytes=60)

    async def pronounce(fragments):
        attempts.append(cache.now)
        return output

    service = QuestionAudioService(
        cache, provider, config, pronounce=pronounce, pronunciation_identity="fixture"
    )
    for moment in (0, 61, 182, 243, 304):
        cache.now = moment
        await service.get(source)
    assert attempts == [0, 61, 182]
    assert len(provider.calls) == 1


async def test_changed_model_has_an_independent_attempt_window():
    cache, provider, attempts = ExpiringCache(), Synthesizer(), []
    source = question()

    async def pronounce(fragments):
        attempts.append(cache.now)
        return None

    for identity, moment in (("old", 0), ("old", 61), ("old", 182), ("new", 183)):
        cache.now = moment
        await QuestionAudioService(
            cache, provider, settings(), pronounce=pronounce, pronunciation_identity=identity
        ).get(source)
    assert attempts == [0, 61, 182, 183]
    assert len(provider.calls) == 2


async def test_question_without_model_fragments_never_consumes_an_attempt():
    cache, provider, attempts = ExpiringCache(), Synthesizer(), []
    source = question("세션 저장소를 설명해 주세요.")

    async def pronounce(fragments):
        attempts.append(fragments)
        return None

    service = QuestionAudioService(
        cache, provider, settings(), pronounce=pronounce, pronunciation_identity="fixture"
    )
    await service.get(source)
    cache.now = 182
    await service.get(source)
    assert not attempts
    assert len(provider.calls) == 1


async def test_identity_without_a_pronouncer_is_cache_only():
    cache, provider = ExpiringCache(), Synthesizer()
    service = QuestionAudioService(cache, provider, settings(), pronunciation_identity="fixture")
    with pytest.raises(TtsError, match="pronunciation_unavailable"):
        await service.get(question())
    assert not provider.calls


@pytest.mark.parametrize("recovered", [False, True])
async def test_model_finishing_after_its_original_epoch_does_not_reinsert_audio(recovered):
    cache, provider, attempts = ExpiringCache(), Synthesizer(), []
    source = question()

    async def pronounce(fragments):
        attempts.append(cache.now)
        if len(attempts) > 1:
            cache.now = 3601
            if recovered:
                return ("서킷 브레이커",)
        return None

    service = QuestionAudioService(
        cache, provider, settings(), pronounce=pronounce, pronunciation_identity="fixture"
    )
    first = await service.get(source)
    cache.now = 3599
    second = await service.get(source)
    assert (second.data != first.data) is recovered
    assert len(provider.calls) == (2 if recovered else 1)
    assert await cache.get(service._key(source)) is None
    assert await cache.get(service._key(source) + ":fallback") is None
    assert await cache.get(service._key(source) + ":pronunciation-attempts") is None


async def test_fallback_read_pins_the_epoch_before_the_following_state_read(monkeypatch):
    cache, provider, attempts = ExpiringCache(), Synthesizer(), []
    source = question()

    async def pronounce(fragments):
        attempts.append(cache.now)
        return None

    service = QuestionAudioService(
        cache, provider, settings(), pronounce=pronounce, pronunciation_identity="fixture"
    )
    first = await service.get(source)
    original_read = service._read_fallback

    async def read_at_expiry(key, current):
        fallback = await original_read(key, current)
        if fallback is not None:
            cache.now = 3601
        return fallback

    monkeypatch.setattr(service, "_read_fallback", read_at_expiry)
    cache.now = 3599
    assert (await service.get(source)).data == first.data
    assert attempts == [0]
    assert len(provider.calls) == 1
    assert await cache.get(service._key(source)) is None
    assert await cache.get(service._key(source) + ":fallback") is None
    assert await cache.get(service._key(source) + ":pronunciation-attempts") is None
