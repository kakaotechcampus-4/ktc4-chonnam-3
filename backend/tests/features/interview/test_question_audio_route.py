import pytest
from pydantic import SecretStr

from app.db.models import InterviewTurn
from app.features.interview.router import router
from app.features.interview.tts_budget import RedisCharacterBudget, initialize_budget
from app.integrations.tts.google import SpeechAudio, TtsError

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
    interview = await make_interview(db, run, [repo], current_turn=1)
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
