import asyncio
from dataclasses import replace
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
from app.integrations.tts.pronunciation import SpeechFragment


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

    async def ttl(self, key):
        return 3600 if key in self.values else -2

    async def execute_command(self, command, script, count, key, owner):
        if command == "SET":
            if script not in self.values:
                return None
            self.values[script] = str(count).encode()
            return True
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


async def test_question_audio_synthesizes_korean_pronunciation_and_reuses_mp3():
    provider = Synthesizer()
    source = question(
        text="https://example.com/api/v1/users 경로로 GET 요청을 보낼 때의 처리를 설명해 주세요."
    )
    service = QuestionAudioService(Cache(), provider, config())

    first = await service.get(source)
    replay = await service.get(source)

    assert first.data == replay.data == b"ID3audio"
    assert provider.calls == [
        (
            "에이치티티피에스 이그잼플 닷컴의 에이피아이 브이일 유저스 경로로 "
            "겟 요청을 보낼 때의 처리를 설명해 주세요.",
            "tech_lead",
        )
    ]
    assert source.text == (
        "https://example.com/api/v1/users 경로로 GET 요청을 보낼 때의 처리를 설명해 주세요."
    )


async def test_concurrent_audio_runs_one_pronunciation_request_and_one_synthesis():
    provider = Synthesizer()
    source = question(text="circuit breaker의 역할과 YAML 설정을 설명해 주세요.")
    model_inputs = []
    entered = asyncio.Event()
    release = asyncio.Event()

    async def pronounce(terms):
        model_inputs.append(terms)
        entered.set()
        await release.wait()
        pronunciation = {
            "circuit": "서킷",
            "breaker": "브레이커",
            "circuit breaker": "서킷 브레이커",
        }
        return tuple(pronunciation[term.text] for term in terms)

    service = QuestionAudioService(
        Cache(), provider, config(), pronounce=pronounce, pronunciation_identity="test-low"
    )
    async with asyncio.TaskGroup() as tasks:
        first = tasks.create_task(service.get(source))
        async with asyncio.timeout(1):
            await entered.wait()
        second = tasks.create_task(service.get(source))
        await asyncio.sleep(0)
        release.set()

    assert first.result().data == second.result().data == (await service.get(source)).data
    assert [" ".join(term.text for term in terms) for terms in model_inputs] == ["circuit breaker"]
    assert all(isinstance(term, SpeechFragment) for term in model_inputs[0])
    assert provider.calls == [("서킷 브레이커의 역할과 야믈 설정을 설명해 주세요.", "tech_lead")]


async def test_new_acronym_and_name_preserve_korean_numbers_and_reuse_audio():
    provider = Synthesizer()
    raw = (
        "QUIC 방식과 OpenTelemetry 도구를 사용하고, "
        "지연 시간을 250ms 이하로 유지한 이유를 설명해 주세요."
    )
    source = question(text=raw)
    model_inputs = []

    async def pronounce(fragments):
        model_inputs.append(fragments)
        pronunciation = {"QUIC": "퀵", "OpenTelemetry": "오픈텔레메트리"}
        return tuple(pronunciation[fragment.text] for fragment in fragments)

    service = QuestionAudioService(
        Cache(), provider, config(), pronounce=pronounce, pronunciation_identity="test-low"
    )
    first = await service.get(source)
    replay = await service.get(source)

    assert first.data == replay.data == b"ID3audio"
    assert len(model_inputs) == 1
    assert tuple(fragment.text for fragment in model_inputs[0]) == ("QUIC", "OpenTelemetry")
    assert all(fragment.kind and fragment.context for fragment in model_inputs[0])
    assert provider.calls == [
        (
            "퀵 방식과 오픈텔레메트리 도구를 사용하고 "
            "지연 시간을 이백오십 밀리초 이하로 유지한 이유를 설명해 주세요.",
            "tech_lead",
        )
    ]
    assert source.text == raw


async def test_unknown_domain_and_path_names_keep_their_structure_after_pronunciation():
    provider = Synthesizer()
    raw = "https://nebula.dev/api/v1/stream_ingest 경로로 GET 요청을 보내는 이유를 설명해 주세요."
    model_inputs = []

    async def pronounce(fragments):
        model_inputs.append(fragments)
        pronunciation = {"nebula": "네뷸라", "stream": "스트림", "ingest": "인제스트"}
        return tuple(pronunciation[fragment.text] for fragment in fragments)

    service = QuestionAudioService(
        Cache(), provider, config(), pronounce=pronounce, pronunciation_identity="test-low"
    )
    source = question(text=raw)
    first = await service.get(source)
    replay = await service.get(source)

    assert first.data == replay.data == b"ID3audio"
    assert len(model_inputs) == 1
    fragments = model_inputs[0]
    assert tuple(fragment.text for fragment in fragments) == ("nebula", "stream", "ingest")
    assert tuple(fragment.kind for fragment in fragments) == ("domain", "path", "path")
    assert provider.calls == [
        (
            "에이치티티피에스 네뷸라 닷 데브의 에이피아이 브이일 스트림 인제스트 경로로 "
            "겟 요청을 보내는 이유를 설명해 주세요.",
            "tech_lead",
        )
    ]
    assert source.text == raw


async def test_old_symbol_narration_cache_is_replaced_and_new_audio_is_reused(monkeypatch):
    from app.features.interview import question_audio

    cache, provider = Cache(), Synthesizer()
    source = question(text="/api/users_read 경로를 설명해 주세요.")
    service = QuestionAudioService(cache, provider, config())
    with monkeypatch.context() as previous_policy:
        previous_policy.setattr(question_audio, "QUESTION_SPEECH_VERSION", "question-speech.v2")
        cache.values[service._key(source)] = b"audio/mpeg\nID3old-symbol-audio"

    first = await service.get(source)
    replay = await service.get(source)

    assert first.data == replay.data == b"ID3audio"
    assert provider.calls == [("에이피아이 유저스 리드 경로를 설명해 주세요.", "tech_lead")]


async def test_superseded_question_is_not_synthesized_after_pronunciation():
    cache, provider = Cache(), Synthesizer()
    source = question(text="circuit breaker의 역할을 설명해 주세요.")
    current = True

    async def pronounce(terms):
        nonlocal current
        current = False
        return None

    async def check_current():
        return current

    service = QuestionAudioService(
        cache, provider, config(), pronounce=pronounce, pronunciation_identity="test-low"
    )

    with pytest.raises(TtsError, match="source_changed"):
        await service.get(source, check_current=check_current)

    assert provider.calls == []
    assert not any(value.startswith(b"audio/") for value in cache.values.values())


@pytest.mark.parametrize("times_out", [False, True])
async def test_unavailable_pronunciation_keeps_local_rules_and_replays_the_fallback(times_out):
    provider = Synthesizer()
    source = question(text="circuit breaker의 역할과 YAML 설정을 설명해 주세요.")
    model_inputs = []

    async def pronounce(terms):
        model_inputs.append(terms)
        if times_out:
            raise TimeoutError
        return None

    service = QuestionAudioService(
        Cache(), provider, config(), pronounce=pronounce, pronunciation_identity="test-low"
    )
    first = await service.get(source)
    replay = await service.get(source)

    assert first.data == replay.data == b"ID3audio"
    assert len(model_inputs) == 1
    assert provider.calls == [("circuit breaker의 역할과 야믈 설정을 설명해 주세요.", "tech_lead")]


async def test_question_audio_falls_back_to_original_when_local_expansion_exceeds_byte_limit():
    provider = Synthesizer()
    source = question(text="inference를 설명해 주세요.")
    settings = replace(config(), max_text_bytes=len(source.text.encode()))
    assert len("인퍼런스를 설명해 주세요.".encode()) > settings.max_text_bytes
    service = QuestionAudioService(Cache(), provider, settings)

    assert (await service.get(source)).data == b"ID3audio"
    assert provider.calls == [(source.text, "tech_lead")]


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
async def test_failed_owner_cooldown_is_checked_after_waiter_acquires_lock():
    class CooldownRace(Cache):
        async def set(self, key, value, *, ex, nx=False):
            if nx:
                # 직전 작업의 실패 표시가 잠금 획득 직전에 기록된 상황이다.
                await super().set(key.removesuffix(":lock") + ":failed", b"1", ex=30)
            return await super().set(key, value, ex=ex, nx=nx)

    provider = Synthesizer()
    service = QuestionAudioService(CooldownRace(), provider, config())

    with pytest.raises(TtsError, match="temporarily_unavailable"):
        await service.get(question())

    assert provider.calls == []


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

    settings = replace(config(), timeout_seconds=0.01)
    service = QuestionAudioService(cache, Waiting(), settings)
    source = question()
    with pytest.raises(TtsError, match="timeout"):
        await service.get(source)
    with pytest.raises(TtsError, match="temporarily_unavailable"):
        await service.get(source)
    assert len(calls) == 1
    assert not any(key.endswith(":lock") for key in cache.values)
