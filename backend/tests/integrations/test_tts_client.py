import base64
import json

import httpx
import pytest
from pydantic import SecretStr

from app.integrations.tts.google import CharacterReservation, GoogleTTSClient, TtsError, TTSSettings

VOICES = {
    "tech_lead": "ko-KR-Chirp3-HD-Charon",
    "domain_lead": "ko-KR-Chirp3-HD-Kore",
    "hr_manager": "ko-KR-Chirp3-HD-Aoede",
}


def settings(**kwargs):
    fields = dict(
        voice_map=VOICES,
        api_key=SecretStr("tts-secret"),
        monthly_character_limit=1000,
        budget_project="unit-google",
    )
    fields.update(kwargs)
    return TTSSettings(**fields)


class Budget:
    def __init__(self):
        self.reserved = 0
        self.outcomes = []

    async def reserve(self, text):
        self.reserved += len(text)
        return CharacterReservation("test", len(text), "unit")

    async def settle(self, receipt, outcome):
        self.outcomes.append(outcome)


def make_client(config, transport, budget=None):
    return GoogleTTSClient(config, transport, budget=budget or Budget())


@pytest.mark.asyncio
async def test_persona_voice_and_original_text_are_sent_without_secret_in_url():
    requests = []

    def respond(request):
        requests.append(request)
        assert request.url == "https://texttospeech.googleapis.com/v1/text:synthesize"
        assert request.headers["x-goog-api-key"] == "tts-secret"
        body = json.loads(request.content)
        assert body["input"] == {"text": "Redis를 선택한 이유는 무엇인가요?"}
        assert body["voice"] == {"languageCode": "ko-KR", "name": VOICES["domain_lead"]}
        assert body["audioConfig"] == {"audioEncoding": "MP3"}
        return httpx.Response(200, json={"audioContent": base64.b64encode(b"ID3audio").decode()})

    audio = await make_client(settings(), httpx.MockTransport(respond)).synthesize(
        "Redis를 선택한 이유는 무엇인가요?", "domain_lead"
    )
    assert audio.data == b"ID3audio"
    assert audio.mime_type == "audio/mpeg"
    assert audio.voice_id == VOICES["domain_lead"]
    assert len(requests) == 1


@pytest.mark.asyncio
async def test_oauth_token_uses_authorization_header():
    def respond(request):
        assert request.headers["authorization"] == "Bearer oauth-secret"
        assert request.headers["x-goog-user-project"] == "unit-google"
        assert "x-goog-api-key" not in request.headers
        return httpx.Response(200, json={"audioContent": "SUQzYXVkaW8="})

    config = settings(api_key=None, access_token=SecretStr("oauth-secret"))
    await make_client(config, httpx.MockTransport(respond)).synthesize("질문", "tech_lead")


@pytest.mark.parametrize(
    "body", [{}, {"audioContent": "??invalid"}, {"audioContent": ""}, {"audioContent": 42}]
)
@pytest.mark.asyncio
async def test_invalid_audio_never_becomes_success(body):
    client = make_client(settings(), httpx.MockTransport(lambda r: httpx.Response(200, json=body)))
    with pytest.raises(TtsError, match="invalid_response"):
        await client.synthesize("질문", "tech_lead")


@pytest.mark.asyncio
async def test_provider_body_is_not_exposed():
    client = make_client(
        settings(), httpx.MockTransport(lambda r: httpx.Response(403, text="tts-secret"))
    )
    with pytest.raises(TtsError) as got:
        await client.synthesize("질문", "tech_lead")
    assert got.value.reason == "unauthorized"
    assert "tts-secret" not in str(got.value)


@pytest.mark.asyncio
async def test_text_limit_and_unknown_persona_fail_before_network():
    calls = []
    client = make_client(settings(max_text_bytes=4), httpx.MockTransport(lambda r: calls.append(r)))
    with pytest.raises(TtsError, match="text_too_large"):
        await client.synthesize("질문질문", "tech_lead")
    with pytest.raises(TtsError, match="unknown_persona"):
        await client.synthesize("a", "unknown")
    assert calls == []


@pytest.mark.asyncio
async def test_audio_limit_applies_to_decoded_content():
    client = make_client(
        settings(max_audio_bytes=2),
        httpx.MockTransport(lambda r: httpx.Response(200, json={"audioContent": "SUQzYXVkaW8="})),
    )
    with pytest.raises(TtsError, match="audio_too_large"):
        await client.synthesize("질문", "tech_lead")


def test_voice_configuration_and_credentials_are_required():
    with pytest.raises(ValueError):
        TTSSettings(voice_map=VOICES)
    with pytest.raises(ValueError):
        TTSSettings(voice_map={"tech_lead": VOICES["tech_lead"]}, api_key=SecretStr("key"))


@pytest.mark.asyncio
async def test_no_budget_or_non_chirp_voice_never_reaches_provider():
    calls = []
    transport = httpx.MockTransport(lambda r: calls.append(r))
    with pytest.raises(TtsError, match="budget_unavailable"):
        await GoogleTTSClient(settings(), transport).synthesize("질문", "tech_lead")
    wrong = dict(VOICES, tech_lead="ko-KR-Studio-A")
    with pytest.raises(TtsError, match="unsupported_free_voice"):
        await make_client(settings(voice_map=wrong), transport).synthesize("질문", "tech_lead")
    assert calls == []


@pytest.mark.asyncio
async def test_unknown_provider_failure_keeps_reservation_and_records_uncertainty():
    budget = Budget()
    client = make_client(
        settings(), httpx.MockTransport(lambda r: httpx.Response(200, json={})), budget
    )
    with pytest.raises(TtsError, match="invalid_response"):
        await client.synthesize("가 나\n", "tech_lead")
    assert budget.reserved == 4
    assert budget.outcomes == ["uncertain"]
