import asyncio
from uuid import uuid4

import httpx
import pytest
from anyio import CancelScope
from pydantic import SecretStr
from redis.exceptions import RedisError

from app.features.interview.question_audio import AudioQuestion, QuestionAudioService
from app.integrations.tts.google import (
    CharacterReservation,
    GoogleTTSClient,
    SpeechAudio,
    TtsError,
    TTSSettings,
)


class Cache:
    def __init__(self):
        self.values = {}

    async def get(self, key):
        return self.values.get(key)

    async def set(self, key, value, *, ex, nx=False):
        if nx and key in self.values:
            return False
        self.values[key] = value.encode() if isinstance(value, str) else value
        return True

    async def execute_command(self, command, script, count, key, owner):
        if self.values.get(key) == owner.encode():
            self.values.pop(key)
            return 1
        return 0


class Synthesizer:
    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    async def synthesize(self, text, persona):
        self.calls.append((text, persona))
        await asyncio.sleep(0.01)
        if self.fail:
            raise TtsError("provider_error")
        return SpeechAudio(b"ID3audio", "audio/mpeg", "voice", "test")


def config():
    return TTSSettings(
        voice_map={"tech_lead": "voice-a", "domain_lead": "voice-b", "hr_manager": "voice-c"},
        api_key=SecretStr("key"),
    )


def question(**kwargs):
    return AudioQuestion(
        interview_id=kwargs.get("interview_id", uuid4()),
        turn_no=1,
        turn_id=uuid4(),
        text=kwargs.get("text", "질문"),
        persona="tech_lead",
    )


@pytest.mark.asyncio
async def test_concurrent_audio_requests_synthesize_once_and_release_lock():
    cache, provider = Cache(), Synthesizer()
    service = QuestionAudioService(cache, provider, config())
    source = question()
    first, second = await asyncio.gather(service.get(source), service.get(source))
    assert first.data == second.data == b"ID3audio"
    assert provider.calls == [("질문", "tech_lead")]
    assert not any(key.endswith(":lock") for key in cache.values)


@pytest.mark.asyncio
async def test_cache_is_bound_to_interview_text_and_voice():
    cache, provider = Cache(), Synthesizer()
    service = QuestionAudioService(cache, provider, config())
    a = question()
    await service.get(a)
    await service.get(a)
    await service.get(question(text="다른 질문", interview_id=a.interview_id))
    await service.get(question())
    assert len(provider.calls) == 3


@pytest.mark.asyncio
async def test_failed_synthesis_releases_lock_and_does_not_cache_success():
    cache, provider = Cache(), Synthesizer(fail=True)
    service = QuestionAudioService(cache, provider, config())
    with pytest.raises(TtsError, match="provider_error"):
        await service.get(question())
    assert not any(key.endswith(":lock") for key in cache.values)
    assert not any(value.startswith(b"audio/") for value in cache.values.values())


@pytest.mark.asyncio
async def test_source_change_after_synthesis_prevents_publish():
    cache, provider = Cache(), Synthesizer()
    service = QuestionAudioService(cache, provider, config())

    async def stale():
        return False

    with pytest.raises(TtsError, match="source_changed"):
        await service.get(question(), check_current=stale)
    assert not any(value.startswith(b"audio/") for value in cache.values.values())


@pytest.mark.asyncio
async def test_cancelled_request_releases_its_own_lock():
    cache = Cache()
    entered = asyncio.Event()

    class Waiting:
        async def synthesize(self, text, persona):
            entered.set()
            await asyncio.sleep(100)

    service = QuestionAudioService(cache, Waiting(), config())
    task = asyncio.create_task(service.get(question()))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not any(key.endswith(":lock") for key in cache.values)


async def test_cancel_after_provider_success_finishes_settlement_and_caches_before_propagating():
    entered, release = asyncio.Event(), asyncio.Event()

    class Budget:
        reserved = 0
        settled = 0

        async def reserve(self, text):
            self.reserved += len(text)
            return CharacterReservation("fixture", len(text), "fixture")

        async def settle(self, receipt, outcome):
            entered.set()
            await release.wait()
            assert outcome == "success"
            self.settled += 1

    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(200, json={"audioContent": "SUQzYXVkaW8="})

    settings = TTSSettings(
        voice_map={p: "ko-KR-Chirp3-HD-Charon" for p in ("tech_lead", "domain_lead", "hr_manager")},
        api_key=SecretStr("fixture"),
        monthly_character_limit=100,
        budget_project="fixture",
    )
    cache, budget, source = Cache(), Budget(), question()
    service = QuestionAudioService(
        cache, GoogleTTSClient(settings, httpx.MockTransport(respond), budget=budget), settings
    )
    task = asyncio.create_task(service.get(source))
    await entered.wait()
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done()
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    replay = await service.get(source)
    assert replay.data == b"ID3audio"
    assert len(calls) == budget.settled == 1 and budget.reserved == 2
    assert not any(key.endswith(":lock") for key in cache.values)


async def test_cancel_during_success_cache_write_keeps_audio_for_zero_provider_replay():
    entered, release = asyncio.Event(), asyncio.Event()

    class SlowCache(Cache):
        async def set(self, key, value, *, ex, nx=False):
            if isinstance(value, bytes) and value.startswith(b"audio/"):
                entered.set()
                await release.wait()
            return await super().set(key, value, ex=ex, nx=nx)

    cache, provider, source = SlowCache(), Synthesizer(), question()
    service = QuestionAudioService(cache, provider, config())
    task = asyncio.create_task(service.get(source))
    await entered.wait()
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert (await service.get(source)).data == b"ID3audio"
    assert len(provider.calls) == 1


async def test_successful_audio_is_returned_when_only_cache_write_is_unavailable():
    class BrokenCache(Cache):
        async def set(self, key, value, *, ex, nx=False):
            if isinstance(value, bytes) and value.startswith(b"audio/"):
                raise RedisError("private failure must not be logged")
            return await super().set(key, value, ex=ex, nx=nx)

    provider = Synthesizer()
    audio = await QuestionAudioService(BrokenCache(), provider, config()).get(question())
    assert audio.data == b"ID3audio" and len(provider.calls) == 1


async def test_source_check_timeout_never_caches_or_returns_unverified_audio(monkeypatch):
    import app.integrations.tts.google as module

    monkeypatch.setattr(module, "FINALIZATION_TIMEOUT_SECONDS", 0.02)
    cache, provider = Cache(), Synthesizer()

    async def unavailable():
        await asyncio.sleep(100)

    async with asyncio.timeout(0.5):
        with pytest.raises(TtsError, match="source_check_unavailable"):
            await QuestionAudioService(cache, provider, config()).get(
                question(), check_current=unavailable
            )
    assert not any(value.startswith(b"audio/") for value in cache.values.values())


async def test_anyio_cancellation_after_paid_audio_keeps_cache_and_propagates():
    class CancellingCache(Cache):
        scope = None

        async def set(self, key, value, *, ex, nx=False):
            if isinstance(value, bytes) and value.startswith(b"audio/"):
                self.scope.cancel()
            return await super().set(key, value, ex=ex, nx=nx)

    cache, provider, source = CancellingCache(), Synthesizer(), question()
    service = QuestionAudioService(cache, provider, config())
    reached_after_get = False
    with CancelScope() as scope:
        cache.scope = scope
        await service.get(source)
        reached_after_get = True
    assert scope.cancel_called and not reached_after_get
    assert (await service.get(source)).data == b"ID3audio"
    assert len(provider.calls) == 1


async def test_outer_timeout_cools_down_before_another_paid_synthesis(monkeypatch):
    from app.features.interview import question_audio

    monkeypatch.setattr(question_audio, "FINALIZATION_TIMEOUT_SECONDS", 0.01)
    cache = Cache()
    calls = []

    class Waiting:
        async def synthesize(self, text, persona):
            calls.append(text)
            await asyncio.sleep(100)

    from dataclasses import replace

    settings = replace(config(), timeout_seconds=0.01)
    service = QuestionAudioService(cache, Waiting(), settings)
    source = question()
    with pytest.raises(TtsError, match="timeout"):
        await service.get(source)
    with pytest.raises(TtsError, match="temporarily_unavailable"):
        await service.get(source)
    assert len(calls) == 1
    assert not any(key.endswith(":lock") for key in cache.values)
