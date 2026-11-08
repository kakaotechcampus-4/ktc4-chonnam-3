"""기존 MLAPI STT 주소 호환과 전용 자격 증명의 경계를 검증한다."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings

LEGACY = "https://legacy.example/whisper-model/v1"


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch):
    for name in (
        "STT_PROVIDER",
        "STT_BASE_URL",
        "STT_API_KEY",
        "STT_MODEL",
        "STT_LANGUAGE",
        "WHISPER_LARGE_V3_PROXY_URL",
        "PROXY_TOKEN",
        "OPENAI_API_KEY",
        "VISION_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)


def test_legacy_whisper_dotenv_alias_resolves_matching_common_credentials(tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        f"Whisper_Large_v3_PROXY_URL={LEGACY}/\n"
        "PROXY_TOKEN=common-fixture-secret\nSTT_PROVIDER=mlapi\n",
        encoding="utf-8",
    )
    settings = Settings(_env_file=env)
    resolved = settings.require_stt()
    assert resolved.stt_base_url == "https://legacy.example/whisper-model"
    assert resolved.stt_api_key.get_secret_value() == "common-fixture-secret"
    assert resolved.stt_provider == "mlapi"
    assert resolved.stt_model == "whisper-large-v3"
    assert resolved.stt_language == "korean"
    for value in (LEGACY, "legacy.example", "common-fixture-secret"):
        assert value not in repr(settings) and value not in repr(resolved)


def test_explicit_stt_pair_wins_without_mutating_cached_settings():
    settings = Settings(
        _env_file=None,
        stt_provider="mlapi",
        stt_base_url="https://dedicated.example/custom/v1/",
        stt_api_key="dedicated-secret",
        whisper_large_v3_proxy_url=LEGACY,
        proxy_token="common-secret",
    )
    before = settings.model_dump()
    resolved = settings.require_stt()
    assert resolved.stt_base_url == "https://dedicated.example/custom"
    assert resolved.stt_api_key.get_secret_value() == "dedicated-secret"
    assert settings.model_dump() == before


@pytest.mark.parametrize("key", [None, "", "   "])
def test_explicit_stt_endpoint_never_inherits_common_proxy_credentials(key):
    settings = Settings(
        _env_file=None,
        stt_provider="mlapi",
        stt_base_url="https://dedicated.example/v1",
        stt_api_key=key,
        whisper_large_v3_proxy_url=LEGACY,
        proxy_token="common-secret",
    )
    with pytest.raises(ValueError) as caught:
        settings.require_stt()
    assert "dedicated.example" not in str(caught.value)
    assert "common-secret" not in str(caught.value)


def test_legacy_endpoint_prefers_explicit_stt_key_over_shared_token():
    resolved = Settings(
        _env_file=None,
        stt_provider="mlapi",
        whisper_large_v3_proxy_url=LEGACY,
        proxy_token="common-secret",
        stt_api_key="dedicated-secret",
    ).require_stt()
    assert resolved.stt_api_key.get_secret_value() == "dedicated-secret"


@pytest.mark.parametrize("url", [None, "", "   "])
def test_absent_legacy_endpoint_does_not_activate_shared_or_other_provider_secrets(url):
    settings = Settings(
        _env_file=None,
        stt_provider="mlapi",
        whisper_large_v3_proxy_url=url,
        proxy_token="common-secret",
        openai_api_key="llm-secret",
        vision_api_key="vision-secret",
    )
    with pytest.raises(ValueError):
        settings.require_stt()


@pytest.mark.parametrize("missing", ["stt_provider", "stt_model", "stt_language"])
def test_legacy_alias_does_not_replace_required_stt_configuration(missing):
    fields = {"stt_provider": "mlapi", "stt_model": "whisper-large-v3", "stt_language": "korean"}
    fields[missing] = None
    settings = Settings(
        _env_file=None,
        **fields,
        whisper_large_v3_proxy_url=LEGACY,
        proxy_token="common-secret",
    )
    with pytest.raises(ValueError):
        settings.require_stt()


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://host.example/v1", "https://host.example"),
        ("https://host.example/v1///", "https://host.example"),
        ("https://host.example/tenant/v1/", "https://host.example/tenant"),
        ("https://host.example/tenant/", "https://host.example/tenant"),
        ("https://host.example/v1/tenant", "https://host.example/v1/tenant"),
    ],
)
def test_stt_endpoint_normalization_strips_only_terminal_api_version(url, expected):
    resolved = Settings(
        _env_file=None,
        stt_provider="mlapi",
        stt_base_url=url,
        stt_api_key="dedicated-secret",
    ).require_stt()
    assert resolved.stt_base_url == expected


@pytest.mark.parametrize(
    "url",
    [
        "http://host.example/v1",
        "https://user:secret@host.example/v1",
        "https://host.example/v1?secret=hidden",
    ],
)
def test_legacy_stt_url_still_requires_safe_https_without_disclosing_inputs(url):
    settings = Settings(
        _env_file=None,
        stt_provider="mlapi",
        whisper_large_v3_proxy_url=url,
        proxy_token="common-secret",
    )
    with pytest.raises(ValidationError) as caught:
        settings.require_stt()
    for value in (url, "host.example", "common-secret"):
        assert value not in str(caught.value) and value not in repr(caught.value)


def test_legacy_environment_selection_uses_only_the_already_loaded_snapshot(monkeypatch):
    monkeypatch.setenv("WHISPER_LARGE_V3_PROXY_URL", LEGACY)
    monkeypatch.setenv("PROXY_TOKEN", "before-load-secret")
    settings = Settings(_env_file=None, stt_provider="mlapi")
    monkeypatch.setenv("PROXY_TOKEN", "after-load-secret")
    resolved = settings.require_stt()
    assert resolved.stt_api_key.get_secret_value() == "before-load-secret"
