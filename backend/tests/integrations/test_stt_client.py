import httpx
import pytest

from app.core.config import Settings, STTSettings
from app.integrations.stt.client import MlapiSttClient, SttError, SttFailureCause

KEY = "stt-secret-key"
BASE = "https://stt.example.test"
STT_ENV_NAMES = (
    "STT_PROVIDER",
    "STT_BASE_URL",
    "STT_API_KEY",
    "STT_MODEL",
    "STT_LANGUAGE",
    "STT_TIMEOUT_SECONDS",
    "STT_MAX_AUDIO_BYTES",
    "STT_MIN_AUDIO_BYTES",
    "STT_HALLUCINATION_PHRASES",
    "STT_HALLUCINATION_MAX_SECONDS",
)


def _settings(**overrides) -> STTSettings:
    values = {
        "stt_provider": "mlapi",
        "stt_base_url": BASE,
        "stt_api_key": KEY,
        "stt_model": "whisper-large-v3",
        "stt_language": "korean",
        "stt_timeout_seconds": 5.0,
        "stt_max_audio_bytes": 1024,
        "stt_min_audio_bytes": 0,
        "stt_hallucination_phrases": ("감사합니다",),
        "stt_hallucination_max_seconds": 15.0,
    }
    return STTSettings.model_validate(values | overrides)


def _client(handler, **overrides) -> MlapiSttClient:
    return MlapiSttClient(_settings(**overrides), transport=httpx.MockTransport(handler))


def _json(status: int, body) -> httpx.Response:
    return httpx.Response(status, json=body)


async def test_transcribe_returns_stripped_text_and_sends_expected_request():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        seen["body"] = request.read()
        return _json(200, {"text": " 안녕하세요. \n", "usage": {"type": "duration", "seconds": 3}})

    text = await _client(handler).transcribe(b"audio-bytes", "audio/webm;codecs=opus")

    assert text == "안녕하세요."
    assert seen["url"] == f"{BASE}/v1/audio/transcriptions"
    assert seen["auth"] == f"Bearer {KEY}"
    body = seen["body"]
    for part in (b'name="model"', b"whisper-large-v3", b"korean", b'name="return_timestamps"'):
        assert part in body
    assert b'name="file"' in body and b"audio-bytes" in body


@pytest.mark.parametrize(
    ("status", "body", "cause"),
    [
        (401, {"error": {"code": "verification_failed_key"}}, SttFailureCause.UNAUTHORIZED),
        (400, {"detail": "Invalid or unsupported audio file"}, SttFailureCause.INVALID_AUDIO),
        (500, {"error": "boom"}, SttFailureCause.PROVIDER_ERROR),
        (503, {}, SttFailureCause.PROVIDER_ERROR),
        (200, {"text": "   "}, SttFailureCause.EMPTY_TRANSCRIPT),
        (200, {"text": None}, SttFailureCause.INVALID_RESPONSE),
        (200, {"transcript": {"text": "x"}}, SttFailureCause.INVALID_RESPONSE),
        (200, ["text"], SttFailureCause.INVALID_RESPONSE),
    ],
)
async def test_failures_map_to_cause(status, body, cause):
    with pytest.raises(SttError) as caught:
        await _client(lambda request: _json(status, body)).transcribe(b"a", "audio/webm")
    assert caught.value.cause is cause


async def test_non_json_body_is_invalid_response():
    def handler(request):
        return httpx.Response(200, content=b"<html>not json</html>")

    with pytest.raises(SttError) as caught:
        await _client(handler).transcribe(b"a", "audio/webm")
    assert caught.value.cause is SttFailureCause.INVALID_RESPONSE


async def test_timeout_and_network_error_are_distinguished():
    def timeout(request):
        raise httpx.ReadTimeout("slow", request=request)

    def refused(request):
        raise httpx.ConnectError("down", request=request)

    with pytest.raises(SttError) as timed_out:
        await _client(timeout).transcribe(b"a", "audio/webm")
    with pytest.raises(SttError) as down:
        await _client(refused).transcribe(b"a", "audio/webm")
    assert timed_out.value.cause is SttFailureCause.TIMEOUT
    assert down.value.cause is SttFailureCause.PROVIDER_ERROR


@pytest.mark.parametrize(
    ("audio", "cause"),
    [(b"", SttFailureCause.EMPTY_TRANSCRIPT), (b"x" * 1025, SttFailureCause.AUDIO_TOO_LARGE)],
)
async def test_invalid_audio_is_rejected_before_calling_provider(audio, cause):
    def handler(request):
        raise AssertionError("provider must not be called")

    with pytest.raises(SttError) as caught:
        await _client(handler).transcribe(audio, "audio/webm")
    assert caught.value.cause is cause


async def test_error_and_log_do_not_leak_key_or_provider_body(caplog):
    body = {"error": {"message": f"bad key {KEY}", "code": "verification_failed_key"}}
    with caplog.at_level("DEBUG"), pytest.raises(SttError) as caught:
        await _client(lambda request: _json(401, body)).transcribe(b"a", "audio/webm")
    assert KEY not in str(caught.value)
    assert KEY not in caplog.text
    assert "verification_failed_key" not in str(caught.value)


@pytest.fixture
def clean_stt_env(monkeypatch, tmp_path):
    for name in STT_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)  # backend/.env를 읽지 않는다.


def test_missing_stt_settings_fail_only_when_required(clean_stt_env):
    settings = Settings()  # 미설정이어도 앱 설정은 만들어진다.
    assert settings.stt_model == "whisper-large-v3"
    assert settings.stt_language == "korean"
    with pytest.raises(ValueError):
        settings.require_stt()


def test_stt_settings_from_env_and_validation(clean_stt_env, monkeypatch):
    monkeypatch.setenv("STT_PROVIDER", "mlapi")
    monkeypatch.setenv("STT_BASE_URL", f"{BASE}/")
    monkeypatch.setenv("STT_API_KEY", KEY)
    resolved = Settings().require_stt()
    assert resolved.stt_base_url == BASE
    assert resolved.stt_api_key.get_secret_value() == KEY
    assert KEY not in repr(resolved)

    monkeypatch.setenv("STT_BASE_URL", "http://insecure.example.test")
    with pytest.raises(ValueError) as caught:
        Settings().require_stt()
    assert "insecure.example.test" not in str(caught.value)


async def test_audio_shorter_than_configured_minimum_is_empty_without_calling_provider():
    def handler(request):
        raise AssertionError("provider must not be called")

    with pytest.raises(SttError) as caught:
        await _client(handler, stt_min_audio_bytes=10).transcribe(b"x" * 9, "audio/webm")
    assert caught.value.cause is SttFailureCause.EMPTY_TRANSCRIPT

    ok = await _client(
        lambda request: _json(200, {"text": "ok"}), stt_min_audio_bytes=10
    ).transcribe(b"x" * 10, "audio/webm")
    assert ok == "ok"


@pytest.mark.parametrize("text", ["감사합니다.", " 감사합니다 ", "감사 합니다!"])
async def test_known_hallucination_on_short_audio_is_empty(text):
    body = {"text": text, "usage": {"type": "duration", "seconds": 3}}
    with pytest.raises(SttError) as caught:
        await _client(lambda request: _json(200, body)).transcribe(b"x" * 8, "audio/webm")
    assert caught.value.cause is SttFailureCause.EMPTY_TRANSCRIPT


@pytest.mark.parametrize(
    ("body", "audio_size", "overrides"),
    [
        # 오디오가 길면 실제 발화일 수 있어 그대로 둔다.
        ({"text": "감사합니다.", "usage": {"seconds": 60}}, 8, {}),
        # usage가 없으면 크기로 추정한다: 15초 초과로 추정되는 크기.
        ({"text": "감사합니다."}, 4096 * 20, {"stt_max_audio_bytes": 4096 * 30}),
        # 문구가 긴 답변의 일부면 그대로 둔다.
        ({"text": "네, 감사합니다.", "usage": {"seconds": 3}}, 8, {}),
        # 필터를 끄면 그대로 둔다.
        ({"text": "감사합니다.", "usage": {"seconds": 3}}, 8, {"stt_hallucination_phrases": ()}),
    ],
)
async def test_hallucination_filter_does_not_drop_other_text(body, audio_size, overrides):
    text = await _client(lambda request: _json(200, body), **overrides).transcribe(
        b"x" * audio_size, "audio/webm"
    )
    assert text == body["text"].strip()


async def test_hallucination_duration_is_estimated_from_size_without_usage():
    with pytest.raises(SttError) as caught:
        await _client(lambda request: _json(200, {"text": "감사합니다."})).transcribe(
            b"x" * 100, "audio/webm"
        )
    assert caught.value.cause is SttFailureCause.EMPTY_TRANSCRIPT


def test_hallucination_phrases_are_read_from_comma_separated_env(clean_stt_env, monkeypatch):
    assert Settings().stt_hallucination_phrases == ("감사합니다",)
    monkeypatch.setenv("STT_HALLUCINATION_PHRASES", "감사합니다, 시청해 주셔서 감사합니다")
    assert Settings().stt_hallucination_phrases == ("감사합니다", "시청해 주셔서 감사합니다")
    monkeypatch.setenv("STT_HALLUCINATION_PHRASES", "")
    assert Settings().stt_hallucination_phrases == ()
