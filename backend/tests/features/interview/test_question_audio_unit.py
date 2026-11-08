import asyncio
from uuid import uuid4

import pytest
from pydantic import SecretStr

from app.features.interview.question_audio import AudioQuestion, QuestionAudioService
from app.integrations.tts.google import SpeechAudio, TtsError, TTSSettings


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
