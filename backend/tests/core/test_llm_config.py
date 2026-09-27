import math
import os
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import LLMSettings, Settings, get_settings

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
    "LLM_MAX_RETRIES",
)


@pytest.fixture(autouse=True)
def isolated_llm_environment(monkeypatch, tmp_path):
    get_settings.cache_clear()
    for name in LLM_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)
    yield
    get_settings.cache_clear()


def test_llm_settings_require_every_runtime_limit():
    with pytest.raises(ValidationError):
        LLMSettings()


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
        LLMSettings(**values)


def test_call_limits_returns_the_validated_contract():
    settings = LLMSettings(**VALID_SETTINGS)

    limits = settings.call_limits()

    assert limits.timeout_seconds == 12.5
    assert limits.max_output_tokens == 2048
    assert limits.max_input_bytes == 65536
    assert limits.max_response_bytes == 32768


def test_secret_is_not_exposed_by_settings_repr():
    settings = LLMSettings(**VALID_SETTINGS)

    assert "secret-test-key" not in repr(settings)


@pytest.mark.parametrize(
    "values",
    [
        {"openai_api_key": "sk-fixture-missing-fields"},
        {**VALID_SETTINGS, "openai_api_key": ["sk-fixture-invalid-type"]},
    ],
)
@pytest.mark.parametrize("settings_type", [Settings, LLMSettings])
def test_secret_is_not_exposed_by_validation_errors(values, settings_type):
    with pytest.raises(ValidationError) as caught:
        settings = settings_type(**values)
        if isinstance(settings, Settings):
            settings.require_llm()

    rendered_error = f"{caught.value!s}\n{caught.value!r}"
    assert "sk-fixture" not in rendered_error


def test_llm_settings_reject_blank_api_key():
    values = {**VALID_SETTINGS, "openai_api_key": "   "}

    with pytest.raises(ValidationError):
        LLMSettings(**values)


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

    assert isinstance(settings, Settings)
    assert settings.llm_default_model == "environment-model"
    assert settings.openai_api_key.get_secret_value() == "environment-secret"
    assert settings.call_limits().timeout_seconds == 9.5
    get_settings.cache_clear()


@pytest.mark.parametrize("missing", VALID_SETTINGS)
def test_app_settings_defer_missing_llm_requirements_until_use(missing):
    settings = Settings(**{**VALID_SETTINGS, missing: None}, _env_file=None)

    assert settings.api_prefix == "/api"
    with pytest.raises(ValidationError):
        settings.require_llm()
    with pytest.raises(ValidationError):
        settings.call_limits()


@pytest.mark.parametrize("blank", ["", "   "])
def test_blank_llm_values_allow_app_settings_but_prevent_llm_calls(blank):
    settings = Settings(**dict.fromkeys(VALID_SETTINGS, blank), _env_file=None)

    assert settings.openai_api_key is None
    assert settings.llm_timeout_seconds is None
    with pytest.raises(ValidationError):
        settings.call_limits()


def test_app_settings_do_not_invent_runtime_limits():
    settings = Settings(_env_file=None)

    assert settings.llm_default_model == "gpt-5.6-luna"
    assert settings.llm_timeout_seconds is None
    assert settings.llm_max_output_tokens is None
    assert settings.llm_max_input_bytes is None
    assert settings.llm_max_response_bytes is None
    with pytest.raises(ValidationError):
        settings.require_llm()


def test_require_llm_uses_loaded_settings_without_reading_environment_again(monkeypatch):
    settings = Settings(**VALID_SETTINGS, _env_file=None)
    monkeypatch.setenv("OPENAI_API_KEY", "changed-secret")
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "99")

    checked = settings.require_llm()

    assert checked.openai_api_key.get_secret_value() == "secret-test-key"
    assert checked.call_limits().timeout_seconds == 12.5
    assert "secret-test-key" not in repr(settings)


def test_llm_validation_view_does_not_load_environment(monkeypatch):
    for name, value in VALID_SETTINGS.items():
        monkeypatch.setenv(name.upper(), str(value))

    with pytest.raises(ValidationError):
        LLMSettings()


@pytest.mark.parametrize(
    "field", ["llm_max_output_tokens", "llm_max_input_bytes", "llm_max_response_bytes"]
)
@pytest.mark.parametrize("invalid", [True, 1.0])
def test_app_settings_do_not_coerce_invalid_integer_limits(field, invalid):
    with pytest.raises(ValidationError):
        settings = Settings(**{**VALID_SETTINGS, field: invalid}, _env_file=None)
        settings.require_llm()


def test_app_settings_do_not_coerce_boolean_timeout():
    with pytest.raises(ValidationError):
        settings = Settings(**{**VALID_SETTINGS, "llm_timeout_seconds": True}, _env_file=None)
        settings.require_llm()


@pytest.mark.parametrize("retries", [0, 2, True, 1.0])
def test_retry_setting_cannot_change_common_two_attempt_policy(retries):
    with pytest.raises(ValidationError):
        Settings(llm_max_retries=retries, _env_file=None)


def test_fixed_retry_setting_accepts_environment_string(monkeypatch):
    monkeypatch.setenv("LLM_MAX_RETRIES", "1")

    assert get_settings().llm_max_retries == 1


@pytest.mark.parametrize("with_template", [False, True])
def test_app_import_lifespan_and_health_work_without_llm_credentials(tmp_path, with_template):
    backend_root = Path(__file__).resolve().parents[2]
    if with_template:
        (tmp_path / ".env").write_text(
            (backend_root / ".env.example").read_text(encoding="utf-8"), encoding="utf-8"
        )
    environment = {**os.environ, "PYTHONPATH": str(backend_root)}
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "from fastapi.testclient import TestClient\n"
            "from app.main import app\n"
            "with TestClient(app) as client:\n"
            "    response = client.get('/api/health')\n"
            "    assert response.status_code == 200\n"
            "    assert response.json() == {'status': 'ok'}\n",
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert completed.returncode == 0, completed.stderr
