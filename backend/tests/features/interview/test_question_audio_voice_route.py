import pytest
from devon_ai.contracts import AttemptMetadata, ModelResult
from pydantic import SecretStr
from sqlalchemy import select

from app.db.models import InterviewTurn, LLMCallRecord, PromptVersion
from app.features.interview.router import router
from app.features.interview.tts_budget import RedisCharacterBudget, initialize_budget
from app.integrations.tts.google import SpeechAudio, TtsError
from app.llm_tasks import question_pronunciation

from .factories import make_interview, make_repo, make_run, make_user


class Synthesizer:
    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    async def synthesize(self, text, persona):
        self.calls.append((text, persona))
        if self.fail:
            raise TtsError("provider_error")
        return SpeechAudio(b"ID3question", "audio/mpeg", "configured-voice", "google_cloud")


@pytest.fixture
async def source(app, db, client):
    app.include_router(router, prefix="/api")
    app.state.settings.tts_provider = "google_cloud"
    app.state.settings.tts_api_key = SecretStr("test-tts-key")
    app.state.settings.tts_voice_map = {
        "tech_lead": "ko-KR-Chirp3-HD-Charon",
        "domain_lead": "ko-KR-Chirp3-HD-Kore",
        "hr_manager": "ko-KR-Chirp3-HD-Aoede",
    }
    app.state.settings.tts_budget_project = "audio-test"
    app.state.settings.tts_monthly_character_limit = 1000
    await initialize_budget(
        app.state.redis, project="audio-test", remaining_characters=1000, monthly_limit=1000
    )
    app.state.tts_client = Synthesizer()
    run = await make_run(db, await make_user(db))
    repo = await make_repo(db, run)
    interview = await make_interview(db, run, [repo], current_turn=1, answer_mode="voice")
    db.add(
        InterviewTurn(
            interview_session_id=interview.id,
            turn_no=1,
            persona="tech_lead",
            question_text="세션 저장소를 설명해 주세요.",
        )
    )
    await db.commit()
    client.cookies.set("devon_session", await app.state.sessions.create(run.user_id))
    return run, interview, f"/api/interviews/{interview.id}/turns/1/question-audio"


async def test_owned_audio_is_cached_and_private(app, client, source):
    _, _, url = source
    first = await client.get(url)
    second = await client.get(url)
    assert first.status_code == second.status_code == 200
    assert first.content == second.content == b"ID3question"
    assert first.headers["content-type"] == "audio/mpeg"
    assert first.headers["cache-control"] == "private, no-store"
    assert len(app.state.tts_client.calls) == 1
    budget = RedisCharacterBudget(app.state.redis, project="audio-test", monthly_limit=1000)
    assert (
        await app.state.redis.hget(budget.key, "used")
        == str(len("세션 저장소를 설명해 주세요.")).encode()
    )


async def test_question_audio_normalizes_provider_input_without_rewriting_saved_question(
    app, db, client, source
):
    _, interview, url = source
    raw = "inference와 manager를 쓰고, 원문만 인용해 주세요."
    spoken = "인퍼런스와 매니저를 쓰고 원문만 인용해 주세요."
    turn = await db.scalar(
        select(InterviewTurn).where(InterviewTurn.interview_session_id == interview.id)
    )
    turn.question_text = raw
    await db.commit()

    first = await client.get(url)
    replay = await client.get(url)
    detail = await client.get(f"/api/interviews/{interview.id}")

    assert first.status_code == replay.status_code == detail.status_code == 200
    assert first.content == replay.content == b"ID3question"
    assert app.state.tts_client.calls == [(spoken, "tech_lead")]
    assert detail.json()["turns"][0]["question"] == raw
    await db.refresh(turn)
    assert turn.question_text == raw
    budget = RedisCharacterBudget(app.state.redis, project="audio-test", monthly_limit=1000)
    assert await app.state.redis.hget(budget.key, "used") == str(len(spoken)).encode()


@pytest.mark.parametrize("use_override", [False, True])
@pytest.mark.parametrize(
    ("raw", "spoken", "fragments", "pronunciations"),
    [
        (
            "circuit breaker의 역할과 YAML 설정을 설명해 주세요.",
            "서킷 브레이커의 역할과 야믈 설정을 설명해 주세요.",
            ("circuit breaker",),
            ("서킷 브레이커",),
        ),
        (
            "QUIC 방식과 OpenTelemetry 도구를 사용하고, "
            "지연 시간을 250ms 이하로 유지한 이유를 설명해 주세요.",
            "퀵 방식과 오픈텔레메트리 도구를 사용하고 "
            "지연 시간을 이백오십 밀리초 이하로 유지한 이유를 설명해 주세요.",
            ("QUIC", "OpenTelemetry"),
            ("퀵", "오픈텔레메트리"),
        ),
    ],
)
async def test_question_audio_uses_active_pronunciation_prompt_and_records_only_metadata(
    app, db, client, source, monkeypatch, use_override, raw, spoken, fragments, pronunciations
):
    _, interview, url = source
    turn = await db.scalar(
        select(InterviewTurn).where(InterviewTurn.interview_session_id == interview.id)
    )
    assert turn is not None
    turn.question_text = raw
    turn_id, interview_id = turn.id, interview.id
    model, version = "test-pronunciation-model", "question_pronunciation_v2@voice-test"
    task = question_pronunciation.QUESTION_PRONUNCIATION_TASK
    db.add(
        PromptVersion(
            task_name=task, version=version, model=model, template="fixture prompt", is_active=True
        )
    )
    await db.commit()
    settings = app.state.settings
    settings.tts_pronunciation_model = model if use_override else None
    settings.openai_model = "general-model" if use_override else model
    settings.llm_reasoning_effort = "xhigh"
    settings.openai_api_key = SecretStr("test-only-key")
    settings.llm_timeout_seconds = 10
    settings.llm_max_output_tokens = 256
    settings.llm_max_input_bytes = settings.llm_max_response_bytes = 8192
    gateway_requests = []
    private_output = "PRIVATE_RAW_PROVIDER_OUTPUT"

    async def call_model(request, validate, *, attempt_sink, **kwargs):
        gateway_requests.append(request)
        attempt = AttemptMetadata(
            attempt=1,
            provider="test-provider",
            model=model,
            prompt_version=version,
            schema_version=request.schema_version,
            latency_ms=8,
            input_tokens=23,
            output_tokens=7,
            raw_output=private_output,
        )
        attempt_sink.append(attempt)
        output = {f"f{index}": text for index, text in enumerate(pronunciations, start=1)}
        return ModelResult(validate(output), None, (attempt,))

    monkeypatch.setattr(question_pronunciation, "call_model", call_model)
    first = await client.get(url)
    replay = await client.get(url)

    assert first.status_code == replay.status_code == 200
    assert first.content == replay.content == b"ID3question"
    assert app.state.tts_client.calls == [(spoken, "tech_lead")]
    assert len(gateway_requests) == 1
    request = gateway_requests[0]
    assert request.prompt.version == version
    assert set(request.payload) == {"fragments"}
    sent_fragments = request.payload["fragments"]
    assert len(sent_fragments) == len(fragments)
    for index, fragment in enumerate(fragments, start=1):
        sent = sent_fragments[f"f{index}"]
        assert set(sent) == {"text", "kind", "context"}
        assert sent["text"] == fragment
        assert sent["kind"] and sent["context"]
    assert request.limits.reasoning_effort == "low"
    assert settings.require_llm().llm_reasoning_effort == "xhigh"
    detail = await client.get(f"/api/interviews/{interview_id}")
    assert detail.json()["turns"][0]["question"] == raw
    records = (
        await db.scalars(
            select(LLMCallRecord).where(
                LLMCallRecord.interview_session_id == interview_id,
                LLMCallRecord.task_name == task,
            )
        )
    ).all()
    assert len(records) == 1
    record = records[0]
    assert (record.turn_id, record.turn_no, record.failure) == (turn_id, 1, None)
    assert len(record.attempts) == 1
    attempt = record.attempts[0]
    assert (attempt["model"], attempt["input_tokens"], attempt["output_tokens"]) == (model, 23, 7)
    assert "raw_output" not in attempt and private_output not in str(attempt)


async def test_other_user_cannot_read_cached_audio(app, db, client, source):
    _, _, url = source
    assert (await client.get(url)).status_code == 200
    other = await make_user(db)
    await db.commit()
    client.cookies.clear()
    client.cookies.set("devon_session", await app.state.sessions.create(other.id))
    response = await client.get(url)
    assert response.status_code == 404
    assert len(app.state.tts_client.calls) == 1


async def test_audio_requires_authentication(client, source):
    _, _, url = source
    client.cookies.clear()
    assert (await client.get(url)).status_code == 401


async def test_provider_failure_preserves_question_text_and_allows_fallback(app, client, source):
    _, interview, url = source
    app.state.tts_client = Synthesizer(fail=True)
    response = await client.get(url)
    assert response.status_code == 409
    assert response.json()["error"]["reason"] == "not_ready"
    detail = await client.get(f"/api/interviews/{interview.id}")
    assert detail.status_code == 200
    assert detail.json()["turns"][0]["question"] == "세션 저장소를 설명해 주세요."
    budget = RedisCharacterBudget(app.state.redis, project="audio-test", monthly_limit=1000)
    assert (
        await app.state.redis.hget(budget.key, "used")
        == str(len("세션 저장소를 설명해 주세요.")).encode()
    )


async def test_missing_tts_configuration_does_not_call_provider(app, client, source):
    _, _, url = source
    app.state.settings.tts_provider = None
    assert (await client.get(url)).status_code == 409
    assert app.state.tts_client.calls == []


async def test_budget_loss_stops_synthesis_without_new_allowance(app, client, source):
    _, _, url = source
    budget = RedisCharacterBudget(app.state.redis, project="audio-test", monthly_limit=1000)
    await app.state.redis.delete(budget.key)
    assert (await client.get(url)).status_code == 409
    assert app.state.tts_client.calls == []
    assert not await app.state.redis.exists(budget.key)


async def test_existing_cached_audio_does_not_need_a_new_paid_request(app, client, source):
    _, _, url = source
    assert (await client.get(url)).status_code == 200
    budget = RedisCharacterBudget(app.state.redis, project="audio-test", monthly_limit=1000)
    await app.state.redis.delete(budget.key)
    assert (await client.get(url)).status_code == 200
    assert len(app.state.tts_client.calls) == 1
    assert not await app.state.redis.exists(budget.key)


async def test_insufficient_allowance_falls_back_before_provider_call(app, client, source):
    _, _, url = source
    await initialize_budget(
        app.state.redis, project="audio-test", remaining_characters=1, monthly_limit=1000
    )
    assert (await client.get(url)).status_code == 409
    assert app.state.tts_client.calls == []


async def test_ownership_change_during_synthesis_blocks_audio_publish(app, db, client, source):
    _, interview, url = source
    other = await make_user(db)
    await db.commit()
    other_id, interview_id = other.id, interview.id

    class MovingOwner:
        async def synthesize(self, text, persona):
            from app.db.models import InterviewSession

            async with app.state.session_factory.begin() as session:
                row = await session.get(InterviewSession, interview_id)
                row.user_id = other_id
            return SpeechAudio(b"ID3private", "audio/mpeg", "configured-voice", "google_cloud")

    app.state.tts_client = MovingOwner()
    assert (await client.get(url)).status_code == 409
    for key in await app.state.redis.keys("question-audio:*"):
        value = await app.state.redis.get(key)
        assert not value.startswith(b"audio/")
