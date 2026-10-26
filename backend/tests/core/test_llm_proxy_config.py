import pytest
from pydantic import SecretStr, ValidationError

from app.core.config import LLMSettings, Settings

RUNTIME = {
    "openai_api_key": "official-fixture-token",
    "llm_default_model": "official-fixture-model",
    "llm_timeout_seconds": 10,
    "llm_max_output_tokens": 2048,
    "llm_max_input_bytes": 65536,
    "llm_max_response_bytes": 65536,
}
PROXY = {
    "proxy_token": "proxy-fixture-token",
    "chat_proxy_url": "https://proxy.example/namespace/v1/",
    "openai_model": " proxy-fixture-model ",
}


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch, tmp_path):
    for name in (*RUNTIME, *PROXY):
        monkeypatch.delenv(name.upper(), raising=False)
    monkeypatch.chdir(tmp_path)


@pytest.mark.parametrize("official_key", [None, "official-fixture-token"])
def test_proxy_configuration_selects_a_matching_pair_without_mutating_settings(official_key):
    settings = Settings(**{**RUNTIME, **PROXY, "openai_api_key": official_key}, _env_file=None)
    before = settings.model_dump()

    resolved = settings.require_llm()

    assert resolved.openai_api_key.get_secret_value() == PROXY["proxy_token"]
    assert resolved.llm_base_url == "https://proxy.example/namespace/v1"
    assert resolved.llm_default_model == "proxy-fixture-model"
    assert settings.model_dump() == before
    assert settings.call_limits().max_output_tokens == 2048
    for value in (PROXY["proxy_token"], PROXY["chat_proxy_url"], "official-fixture-token"):
        assert value not in repr(settings)
        assert value not in repr(resolved)


@pytest.mark.parametrize("empty", [None, "", "   "])
def test_unconfigured_proxy_preserves_official_connection(empty):
    settings = Settings(
        **RUNTIME, proxy_token=empty, chat_proxy_url=empty, openai_model=empty, _env_file=None
    )

    resolved = settings.require_llm()

    assert resolved.openai_api_key.get_secret_value() == RUNTIME["openai_api_key"]
    assert resolved.llm_base_url == "https://api.openai.com/v1"
    assert resolved.llm_default_model == RUNTIME["llm_default_model"]


@pytest.mark.parametrize("missing", ["proxy_token", "chat_proxy_url"])
@pytest.mark.parametrize("empty", [None, "", "   "])
def test_half_configured_proxy_is_rejected_only_when_llm_is_required(missing, empty):
    settings = Settings(**{**RUNTIME, **PROXY, missing: empty}, _env_file=None)

    assert settings.api_prefix == "/api"
    with pytest.raises(ValueError) as caught:
        settings.require_llm()
    message = f"{caught.value!s}\n{caught.value!r}"
    assert "PROXY_TOKEN" in message and "CHAT_PROXY_URL" in message
    assert PROXY["proxy_token"] not in message and PROXY["chat_proxy_url"] not in message


@pytest.mark.parametrize("suffix", ["", "/", "///"])
def test_base_url_normalization_preserves_namespace_and_version(suffix):
    resolved = LLMSettings(**RUNTIME, llm_base_url=f"https://proxy.example/namespace/v1{suffix}")

    assert resolved.llm_base_url == "https://proxy.example/namespace/v1"


@pytest.mark.parametrize(
    "url",
    [
        "http://proxy.example/v1",
        "https:///v1",
        "https://proxy.example:invalid/v1",
        "https://proxy.example:65536/v1",
        "https://user:secret@proxy.example/v1",
        "https://proxy.example/v1?secret=fixture",
        "https://proxy.example/v1?",
        "https://proxy.example/v1#secret",
        "https://proxy.example/v1#",
        "https://proxy.example/na\tmespace/v1",
        "\nhttps://proxy.example/v1",
        "https://proxy.example/v1\x7f",
        "https://bad host/v1",
        "https://proxy.example\\other/v1",
    ],
)
def test_invalid_proxy_url_is_rejected_without_disclosing_it(url):
    settings = Settings(**{**RUNTIME, **PROXY, "chat_proxy_url": url}, _env_file=None)

    with pytest.raises(ValidationError) as caught:
        settings.require_llm()
    message = f"{caught.value!s}\n{caught.value!r}"
    assert url not in message and PROXY["proxy_token"] not in message
    assert "proxy.example" not in message


def test_environment_overrides_dotenv_and_runtime_resolution_does_not_reload_it(
    monkeypatch, tmp_path
):
    (tmp_path / ".env").write_text(
        "PROXY_TOKEN=file-fixture-token\n"
        "CHAT_PROXY_URL=https://file.example/namespace/v1\n"
        "OPENAI_MODEL=file-fixture-model\n",
        encoding="utf-8",
    )
    for name, value in PROXY.items():
        monkeypatch.setenv(name.upper(), value)
    settings = Settings(**RUNTIME)
    for name in PROXY:
        monkeypatch.setenv(name.upper(), "changed-after-load")

    resolved = settings.require_llm()

    assert isinstance(settings.proxy_token, SecretStr)
    assert resolved.openai_api_key.get_secret_value() == PROXY["proxy_token"]
    assert resolved.llm_base_url == "https://proxy.example/namespace/v1"
    assert resolved.llm_default_model == "proxy-fixture-model"


def test_openai_model_overrides_default_model_for_official_connection():
    resolved = Settings(**RUNTIME, openai_model=" selected-model ", _env_file=None).require_llm()

    assert resolved.llm_default_model == "selected-model"


@pytest.mark.parametrize(
    "missing",
    [
        "llm_timeout_seconds",
        "llm_max_output_tokens",
        "llm_max_input_bytes",
        "llm_max_response_bytes",
    ],
)
def test_proxy_connection_still_requires_each_runtime_limit(missing):
    settings = Settings(**{**RUNTIME, **PROXY, missing: None}, _env_file=None)

    with pytest.raises(ValidationError):
        settings.require_llm()
