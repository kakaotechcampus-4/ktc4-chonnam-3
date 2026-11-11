from types import SimpleNamespace
from uuid import uuid4

import pytest
from devon_ai.contracts import PromptSpec
from sqlalchemy.exc import SQLAlchemyError

from app.core.errors import AppError
from app.features.interview import question_audio
from app.features.interview import router as audio_router
from app.integrations.tts.google import CharacterReservation
from app.shared.enums import Reason

from .test_question_audio_recovery import ExpiringCache, Synthesizer, question, settings


class PromptSession:
    def __init__(self):
        self.version = "question_pronunciation_v2@fixture"
        self.model = "fixture"
        self.fail_identity = False
        self.fail_body = False
        self.fail_source = False
        self.identity_queries = []
        self.body_reads = 0
        self.error = SQLAlchemyError
        self.active_count = 1

    async def execute(self, query, *args):
        self.identity_queries.append(str(query))
        if self.fail_identity:
            raise self.error("fixture")
        return SimpleNamespace(
            mappings=lambda: SimpleNamespace(
                all=lambda: [{"version": self.version, "model": self.model}] * self.active_count
            )
        )

    async def rollback(self):
        pass


class AppSettings:
    tts_pronunciation_model = None

    def __init__(self):
        self.model = "fixture"

    def require_llm(self):
        return SimpleNamespace(llm_default_model=self.model)

    def require_tts(self):
        return settings()


class Budget:
    def __init__(self, *args, **kwargs):
        self.calls = []

    async def reserve(self, text):
        self.calls.append(text)
        return CharacterReservation(str(len(self.calls)), len(text), "fixture")

    async def settle(self, reservation, outcome):
        pass


@pytest.fixture
def harness(monkeypatch):
    db, cache, provider, config = PromptSession(), ExpiringCache(), Synthesizer(), AppSettings()
    source, user, model_calls = question(), SimpleNamespace(id=uuid4()), []
    state = SimpleNamespace(
        settings=config, redis=cache, tts_client=provider, session_factory=object()
    )
    request = SimpleNamespace(app=SimpleNamespace(state=state))

    async def load_question(*args, **kwargs):
        if db.fail_source:
            raise db.error("fixture")
        return source

    async def full_prompt(*args):
        db.body_reads += 1
        if db.fail_body or db.fail_identity:
            raise db.error("fixture")
        return PromptSpec(
            task_name="question_pronunciation",
            version=db.version,
            model=db.model,
            template="fixture",
        )

    async def pronounce(*args, **kwargs):
        model_calls.append(1)
        return None if state.fail_model else ("서킷 브레이커",)

    async def record(*args):
        if state.fail_source_after_record:
            db.fail_source = True

    state.fail_model, state.fail_source_after_record = False, False
    monkeypatch.setattr(audio_router, "load_question", load_question)
    monkeypatch.setattr(audio_router, "RedisCharacterBudget", Budget)
    monkeypatch.setattr(audio_router, "pronounce_fragments", pronounce)
    monkeypatch.setattr(audio_router, "record_question_pronunciation", record)
    monkeypatch.setattr(question_audio, "load_active_prompt", full_prompt)

    async def get():
        return await audio_router.get_question_audio(str(source.interview_id), 1, request, db, user)

    return SimpleNamespace(
        db=db,
        cache=cache,
        provider=provider,
        config=config,
        source=source,
        state=state,
        model_calls=model_calls,
        get=get,
    )


async def test_cached_audio_validates_identity_without_loading_template(harness):
    first = await harness.get()
    assert (await harness.get()).body == first.body
    assert harness.db.body_reads == 1
    assert len(harness.db.identity_queries) == 2
    assert all("template" not in query.lower() for query in harness.db.identity_queries)
    assert len(harness.model_calls) == len(harness.provider.calls) == 1


@pytest.mark.parametrize("error", [SQLAlchemyError, TimeoutError, OSError])
async def test_transient_identity_failure_replays_known_audio_without_new_synthesis(harness, error):
    first = await harness.get()
    harness.db.fail_identity = True
    harness.db.error = error
    assert (await harness.get()).body == first.body
    assert len(harness.provider.calls) == 1
    assert len(harness.model_calls) == 1


@pytest.mark.parametrize("error", [SQLAlchemyError, TimeoutError, OSError])
async def test_transient_identity_failure_with_no_audio_is_controlled_and_uncached(harness, error):
    harness.db.fail_identity = True
    harness.db.error = error
    with pytest.raises(AppError) as caught:
        await harness.get()
    assert caught.value.reason is Reason.NOT_READY
    assert not harness.provider.calls
    assert not harness.cache.values


@pytest.mark.parametrize("error", [SQLAlchemyError, TimeoutError, OSError])
async def test_transient_body_failure_replays_fallback_without_spending_a_model_attempt(
    harness, error
):
    harness.state.fail_model = True
    first = await harness.get()
    harness.cache.now = 61
    harness.db.fail_body = True
    harness.db.error = error
    assert (await harness.get()).body == first.body
    assert len(harness.model_calls) == len(harness.provider.calls) == 1
    harness.cache.now = 92
    harness.db.fail_body = False
    harness.state.fail_model = False
    assert (await harness.get()).body != first.body
    assert len(harness.model_calls) == len(harness.provider.calls) == 2


@pytest.mark.parametrize("change", ["version", "model"])
async def test_verified_prompt_or_configuration_change_invalidates_audio(harness, change):
    await harness.get()
    if change == "version":
        harness.db.version = "question_pronunciation_v2@new"
    else:
        harness.config.model = harness.db.model = "new-model"
    await harness.get()
    assert harness.db.body_reads == 2
    assert len(harness.model_calls) == len(harness.provider.calls) == 2


async def test_configuration_change_cannot_reuse_old_identity_during_database_failure(harness):
    await harness.get()
    harness.config.model = "new-model"
    harness.db.fail_identity = True
    with pytest.raises(AppError) as caught:
        await harness.get()
    assert caught.value.reason is Reason.NOT_READY
    assert len(harness.provider.calls) == 1


async def test_verified_disabled_configuration_retires_the_previous_identity(harness):
    await harness.get()
    harness.db.model = "mismatched-model"
    await harness.get()
    assert len(harness.provider.calls) == 2
    harness.db.fail_identity = True
    with pytest.raises(AppError) as caught:
        await harness.get()
    assert caught.value.reason is Reason.NOT_READY
    assert len(harness.provider.calls) == 2


async def test_cached_identity_expiry_is_not_renewed_by_audio_replays(harness):
    await harness.get()
    harness.cache.now = 1800
    await harness.get()
    harness.cache.now = 3601
    harness.db.fail_identity = True
    with pytest.raises(AppError) as caught:
        await harness.get()
    assert caught.value.reason is Reason.NOT_READY
    assert len(harness.provider.calls) == 1


@pytest.mark.parametrize("error", [SQLAlchemyError, TimeoutError, OSError])
async def test_initial_source_database_failure_is_controlled(harness, error):
    harness.db.fail_source = True
    harness.db.error = error
    with pytest.raises(AppError) as caught:
        await harness.get()
    assert caught.value.reason is Reason.NOT_READY
    assert not harness.provider.calls


@pytest.mark.parametrize("error", [SQLAlchemyError, TimeoutError, OSError])
async def test_final_source_check_still_runs_after_optional_recording(harness, error):
    harness.state.fail_source_after_record = True
    harness.db.error = error
    with pytest.raises(AppError) as caught:
        await harness.get()
    assert caught.value.reason is Reason.NOT_READY
    assert len(harness.provider.calls) == 1


async def test_body_lookup_finishing_after_fallback_expiry_does_not_reinsert_it(
    harness, monkeypatch
):
    harness.state.fail_model = True
    first = await harness.get()
    audio_key = next(
        key for key, value in harness.cache.values.items() if value.startswith(b"audio/")
    )
    harness.cache.now = 3599

    async def expired_lookup(*args):
        harness.cache.now = 3601
        raise SQLAlchemyError("fixture")

    monkeypatch.setattr(question_audio, "load_active_prompt", expired_lookup)
    assert (await harness.get()).body == first.body
    assert len(harness.model_calls) == len(harness.provider.calls) == 1
    assert await harness.cache.get(audio_key) is None
    assert await harness.cache.get(audio_key + ":fallback") is None


@pytest.mark.parametrize("reason", ["model_mismatch", "unsupported_version", "multiple_active"])
async def test_disabled_pronunciation_logs_a_safe_reason(harness, caplog, reason):
    if reason == "model_mismatch":
        harness.db.model = "mismatched-model"
    elif reason == "unsupported_version":
        harness.db.version = "question_pronunciation_v999"
    else:
        harness.db.active_count = 2
    await harness.get()
    assert any(getattr(record, "reason", None) == reason for record in caplog.records)
    assert not harness.model_calls
