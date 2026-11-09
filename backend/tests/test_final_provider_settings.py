"""선택 공급자는 앱 기동과 분리하고 실제 호출 전에 설정을 검증한다."""

import json

import pytest
from pydantic import SecretStr

from app.core.config import Settings


def test_search_settings_use_secret_key_and_explicit_limits():
    settings = Settings(_env_file=None, tavily_api_key="test-secret", tavily_max_results=2)
    search = settings.require_tavily()
    assert isinstance(search.api_key, SecretStr)
    assert search.api_key.get_secret_value() == "test-secret"
    assert search.max_results == 2
    assert "test-secret" not in repr(search)


def test_unconfigured_optional_providers_fail_only_when_requested():
    settings = Settings(_env_file=None)
    for method in (settings.require_tavily, settings.require_vision, settings.require_tts):
        with pytest.raises(ValueError):
            method()


def test_vision_base_url_and_polling_policy_reach_adapter():
    settings = Settings(
        _env_file=None,
        vision_base_url="https://example.mlapi.run",
        vision_api_key="secret",
        vision_max_polls=3,
    )
    vision = settings.require_vision()
    assert vision.base_url == "https://example.mlapi.run"
    assert vision.max_polls == 3
    assert vision.job_path_template == "/v1/jobs/{job_id}"


def test_tts_persona_voice_mapping_parses_json_without_hardcoded_voices():
    voices = {"tech_lead": "voice-a", "domain_lead": "voice-b", "hr_manager": "voice-c"}
    settings = Settings(
        _env_file=None,
        tts_provider="google_cloud",
        tts_api_key="secret",
        tts_voice_map=json.dumps(voices),
    )
    tts = settings.require_tts()
    assert dict(tts.voice_map) == voices
    assert tts.language_code == "ko-KR"


def test_mlapi_document_vision_env_name_uses_common_proxy_token(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "Helpy_Vision_Document_PROXY_URL=https://example.mlapi.run/document-model/v1\n"
        "PROXY_TOKEN=common-vision-test-secret\n",
        encoding="utf-8",
    )
    settings = Settings(_env_file=env_file)
    vision = settings.require_vision()
    assert vision.base_url == "https://example.mlapi.run/document-model"
    assert vision.api_key.get_secret_value() == "common-vision-test-secret"
    assert "example.mlapi.run" not in repr(settings)
    assert "common-vision-test-secret" not in repr(settings)
    assert settings.chat_proxy_url is None


def test_explicit_vision_configuration_has_priority_over_mlapi_fallback():
    settings = Settings(
        _env_file=None,
        vision_base_url="https://explicit.example/namespace/v1/",
        vision_api_key="dedicated-secret",
        proxy_token="common-secret",
        helpy_vision_document_proxy_url="https://fallback.example/namespace/v1",
    )
    vision = settings.require_vision()
    assert vision.base_url == "https://explicit.example/namespace"
    assert vision.api_key.get_secret_value() == "dedicated-secret"
    assert settings.proxy_token.get_secret_value() == "common-secret"


def test_explicit_vision_endpoint_never_receives_implicit_common_credentials():
    settings = Settings(
        _env_file=None,
        vision_base_url="https://explicit.example/namespace/v1",
        proxy_token="common-secret",
        helpy_vision_document_proxy_url="https://fallback.example/namespace/v1",
    )
    with pytest.raises(ValueError):
        settings.require_vision()


@pytest.mark.parametrize("empty", ["", "   ", SecretStr("")])
def test_blank_optional_credentials_are_unset_without_overriding_dedicated_urls(empty):
    settings = Settings(
        _env_file=None,
        tts_access_token=empty,
        tts_api_key="dedicated-tts",
        vision_api_key=empty,
        tavily_api_key=empty,
        helpy_vision_document_proxy_url="https://legacy.example/v1",
        proxy_token="legacy-secret",
    )
    assert settings.tts_access_token is None
    assert settings.tavily_api_key is None
    assert settings.require_vision().api_key.get_secret_value() == "legacy-secret"
    with pytest.raises(ValueError):
        settings.require_tavily()
    explicit = settings.model_copy(update={"vision_base_url": "https://dedicated.example"})
    with pytest.raises(ValueError):
        explicit.require_vision()


def test_blank_env_oauth_token_does_not_mask_api_key(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("TTS_ACCESS_TOKEN=\nTTS_API_KEY=fixture-key\n", encoding="utf-8")
    settings = Settings(_env_file=env_file)
    assert settings.tts_access_token is None
    assert settings.tts_api_key.get_secret_value() == "fixture-key"
