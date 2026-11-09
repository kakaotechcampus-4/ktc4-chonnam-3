"""명시한 모델 슬롯의 주소·모델을 함께 선택하고 다른 공급자 설정은 보존한다."""

import pytest
from pydantic import SecretStr, ValidationError

from app.core.config import Settings


def configured(**changes):
    return Settings(
        _env_file=None,
        **{
            "proxy_token": SecretStr("test-only"),
            "chat_proxy_url": "https://primary.example/v1",
            "openai_model": "primary-model",
            "chat_proxy_url_3": "https://third.example/v1",
            "openai_model_3": "third-model",
            "llm_timeout_seconds": 50,
            "llm_max_output_tokens": 128000,
            "llm_max_input_bytes": 262144,
            "llm_max_response_bytes": 67108864,
            **changes,
        },
    )


def test_selected_slot_uses_its_model_and_endpoint_together():
    settings = configured(llm_connection_slot=3)
    llm = settings.require_llm()
    assert llm.llm_default_model == "third-model"
    assert llm.llm_base_url == "https://third.example/v1"
    assert llm.openai_api_key.get_secret_value() == "test-only"
    assert settings.chat_proxy_url == "https://primary.example/v1"


def test_default_slot_keeps_existing_primary_connection():
    assert configured().require_llm().llm_default_model == "primary-model"


@pytest.mark.parametrize("missing", ["chat_proxy_url_3", "openai_model_3", "proxy_token"])
def test_incomplete_selected_slot_does_not_fall_back_to_another_model(missing):
    with pytest.raises(ValueError):
        configured(llm_connection_slot=3, **{missing: None}).require_llm()


@pytest.mark.parametrize("value", [0, 4, True])
def test_invalid_slot_is_rejected(value):
    with pytest.raises(ValidationError):
        configured(llm_connection_slot=value)


def test_task_timeout_changes_only_the_explicit_task_budget():
    llm = configured(llm_task_timeouts='{"repo_deep":120}').require_llm()
    assert llm.call_limits("repo_deep").timeout_seconds == 120
    assert llm.call_limits("director").timeout_seconds == 50
    assert llm.call_limits().max_output_tokens == 128000


@pytest.mark.parametrize("value", [{"typo_task": 10}, {"repo_deep": False}, {"repo_deep": -1}])
def test_invalid_task_timeouts_are_rejected(value):
    with pytest.raises(ValidationError):
        configured(llm_task_timeouts=value)
