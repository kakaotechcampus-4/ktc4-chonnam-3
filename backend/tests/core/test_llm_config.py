import math

import pytest
from pydantic import ValidationError

from app.core.config import LLMSettings, get_settings

VALID_SETTINGS = {
    "openai_api_key": "secret-test-key",
    "llm_default_model": "test-model",
    "llm_timeout_seconds": 12.5,
    "llm_max_output_tokens": 2048,
    "llm_max_input_bytes": 65536,
    "llm_max_response_bytes": 32768,
}
LLM_ENV_NAMES = (
    "OPENAI_API_KEY",
    "LLM_DEFAULT_MODEL",
    "LLM_TIMEOUT_SECONDS",
    "LLM_MAX_OUTPUT_TOKENS",
    "LLM_MAX_INPUT_BYTES",
    "LLM_MAX_RESPONSE_BYTES",
)


def test_llm_settings_require_every_runtime_limit(monkeypatch):
    for name in LLM_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(ValidationError):
        LLMSettings(_env_file=None)


@pytest.mark.parametrize(
    ("field", "invalid"),
    [
        ("llm_timeout_seconds", 0),
        ("llm_timeout_seconds", math.inf),
        ("llm_timeout_seconds", True),
        ("llm_max_output_tokens", 0),
        ("llm_max_output_tokens", True),
        ("llm_max_output_tokens", 1.0),
        ("llm_max_input_bytes", 0),
        ("llm_max_input_bytes", True),
        ("llm_max_input_bytes", 1.0),
        ("llm_max_response_bytes", 0),
        ("llm_max_response_bytes", True),
        ("llm_max_response_bytes", 1.0),
    ],
)
def test_llm_settings_reject_unbounded_or_non_positive_limits(field, invalid):
    values = {**VALID_SETTINGS, field: invalid}

    with pytest.raises(ValidationError):
        LLMSettings(**values, _env_file=None)


def test_call_limits_returns_the_validated_contract():
    settings = LLMSettings(**VALID_SETTINGS, _env_file=None)

    limits = settings.call_limits()

    assert limits.timeout_seconds == 12.5
    assert limits.max_output_tokens == 2048
    assert limits.max_input_bytes == 65536
    assert limits.max_response_bytes == 32768


def test_secret_is_not_exposed_by_settings_repr():
    settings = LLMSettings(**VALID_SETTINGS, _env_file=None)

    assert "secret-test-key" not in repr(settings)


@pytest.mark.parametrize(
    "values",
    [
        {"openai_api_key": "sk-fixture-missing-fields"},
        {**VALID_SETTINGS, "openai_api_key": ["sk-fixture-invalid-type"]},
    ],
)
def test_secret_is_not_exposed_by_validation_errors(values, monkeypatch):
    for name in LLM_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(ValidationError) as caught:
        LLMSettings(**values, _env_file=None)

    rendered_error = f"{caught.value!s}\n{caught.value!r}"
    assert "sk-fixture" not in rendered_error


def test_llm_settings_reject_blank_api_key():
    values = {**VALID_SETTINGS, "openai_api_key": "   "}

    with pytest.raises(ValidationError):
        LLMSettings(**values, _env_file=None)


def test_get_settings_reads_environment_only_when_called(monkeypatch):
    get_settings.cache_clear()
    for name, value in {
        "OPENAI_API_KEY": "environment-secret",
        "LLM_DEFAULT_MODEL": "environment-model",
        "LLM_TIMEOUT_SECONDS": "9.5",
        "LLM_MAX_OUTPUT_TOKENS": "1024",
        "LLM_MAX_INPUT_BYTES": "8192",
        "LLM_MAX_RESPONSE_BYTES": "4096",
    }.items():
        monkeypatch.setenv(name, value)

    settings = get_settings()

    assert settings.llm_default_model == "environment-model"
    assert settings.openai_api_key.get_secret_value() == "environment-secret"
    assert settings.call_limits().timeout_seconds == 9.5
    get_settings.cache_clear()
