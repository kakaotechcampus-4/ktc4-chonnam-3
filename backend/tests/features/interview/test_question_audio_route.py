"""음성 입력 기반이 없어도 텍스트 면접의 인증·원문·캐시·예산 경계는 지킨다."""

import pytest
from pydantic import SecretStr
from sqlalchemy import select

from app.db.models import InterviewTurn
from app.features.interview.question_audio import AudioQuestion, QuestionAudioService
from app.features.interview.router import router
from app.features.interview.tts_budget import RedisCharacterBudget, initialize_budget

from .factories import make_interview, make_repo, make_run, make_user


class Synthesizer:
    def __init__(self):
        self.calls = []

    async def synthesize(self, text, persona):
        self.calls.append((text, persona))
        raise AssertionError("텍스트 면접의 음성 조회는 공급자를 호출하면 안 됩니다.")


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
    interview = await make_interview(db, run, [repo], current_turn=1, answer_mode="text")
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


def budget(app):
    return RedisCharacterBudget(app.state.redis, project="audio-test", monthly_limit=1000)


async def cached_audio(app, db, interview):
    turn = await db.scalar(
        select(InterviewTurn).where(InterviewTurn.interview_session_id == interview.id)
    )
    question = AudioQuestion(interview.id, 1, turn.id, turn.question_text, turn.persona)
    service = QuestionAudioService(
        app.state.redis, app.state.tts_client, app.state.settings.require_tts()
    )
    # 실제 키·봉투의 캐시를 미리 두어도 텍스트 모드의 조회 권한이 생기지 않는다.
    key = service._key(question)
    await app.state.redis.set(key, b"audio/mpeg\nID3private", ex=60)
    return key


async def test_text_interview_blocks_paid_synthesis_and_preserves_question(app, client, source):
    _, interview, url = source
    before = await app.state.redis.hgetall(budget(app).key)
    assert interview.answer_mode == "text"
    for _ in range(2):
        response = await client.get(url)
        assert response.status_code == 409
        assert response.json()["error"]["reason"] == "not_ready"
    assert app.state.tts_client.calls == []
    assert await app.state.redis.hgetall(budget(app).key) == before
    detail = await client.get(f"/api/interviews/{interview.id}")
    assert detail.status_code == 200
    assert detail.json()["turns"][0]["question"] == "세션 저장소를 설명해 주세요."
    assert await app.state.redis.keys("question-audio:*") == []


async def test_text_mode_does_not_disclose_prepopulated_audio(app, db, client, source):
    _, interview, url = source
    key = await cached_audio(app, db, interview)
    before = await app.state.redis.hgetall(budget(app).key)
    assert (await client.get(url)).status_code == 409
    assert app.state.tts_client.calls == []
    assert await app.state.redis.get(key) == b"audio/mpeg\nID3private"
    assert await app.state.redis.hgetall(budget(app).key) == before


async def test_other_user_cannot_access_text_question_or_cached_audio(app, db, client, source):
    _, interview, url = source
    key = await cached_audio(app, db, interview)
    before = await app.state.redis.hgetall(budget(app).key)
    other = await make_user(db)
    await db.commit()
    client.cookies.clear()
    client.cookies.set("devon_session", await app.state.sessions.create(other.id))
    response = await client.get(url)
    assert response.status_code == 404
    assert app.state.tts_client.calls == []
    assert await app.state.redis.get(key) == b"audio/mpeg\nID3private"
    assert await app.state.redis.hgetall(budget(app).key) == before


async def test_audio_requires_authentication(app, client, source):
    _, _, url = source
    before = await app.state.redis.hgetall(budget(app).key)
    client.cookies.clear()
    assert (await client.get(url)).status_code == 401
    assert app.state.tts_client.calls == []
    assert await app.state.redis.hgetall(budget(app).key) == before


async def test_text_guard_does_not_reinitialize_a_missing_allowance(app, client, source):
    _, _, url = source
    await app.state.redis.delete(budget(app).key)
    assert (await client.get(url)).status_code == 409
    assert app.state.tts_client.calls == []
    assert not await app.state.redis.exists(budget(app).key)


async def test_text_guard_does_not_reserve_a_limited_allowance(app, client, source):
    _, _, url = source
    await initialize_budget(
        app.state.redis, project="audio-test", remaining_characters=1, monthly_limit=1000
    )
    before = await app.state.redis.hgetall(budget(app).key)
    assert (await client.get(url)).status_code == 409
    assert app.state.tts_client.calls == []
    assert await app.state.redis.hgetall(budget(app).key) == before
