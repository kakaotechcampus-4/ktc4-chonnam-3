"""LLM 환경변수의 단일 진입점."""

from functools import lru_cache

from devon_ai.contracts import CallLimits
from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMSettings(BaseSettings):
    """실제 호출에 필요한 비밀값과 유한한 실행 상한을 명시적으로 주입받는다.

    모델이나 운영 제한값을 기본값으로 추정하지 않는다. 설정이 없으면 호출 전에 실패한다.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        # SecretStr 변환 전의 입력도 검증 오류 문자열에 노출되지 않게 한다.
        hide_input_in_errors=True,
    )

    openai_api_key: SecretStr = Field(min_length=1)
    llm_default_model: str = Field(min_length=1)
    llm_timeout_seconds: float = Field(gt=0, allow_inf_nan=False)
    llm_max_output_tokens: int = Field(gt=0)
    llm_max_input_bytes: int = Field(gt=0)
    llm_max_response_bytes: int = Field(gt=0)

    @field_validator("openai_api_key")
    @classmethod
    def validate_api_key(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError("openai_api_key must not be blank")
        return value

    @field_validator("llm_default_model")
    @classmethod
    def validate_model_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("llm_default_model must not be blank")
        return value.strip()

    @field_validator("llm_timeout_seconds", mode="before")
    @classmethod
    def reject_boolean_timeout(cls, value: object) -> object:
        if isinstance(value, bool):
            raise ValueError("llm_timeout_seconds must be a number")
        return value

    @field_validator(
        "llm_max_output_tokens",
        "llm_max_input_bytes",
        "llm_max_response_bytes",
        mode="before",
    )
    @classmethod
    def reject_non_integer_limits(cls, value: object) -> object:
        if isinstance(value, (bool, float)):
            raise ValueError("LLM integer limits must be integers")
        return value

    def call_limits(self) -> CallLimits:
        """AI에는 환경변수나 비밀키 대신 공급자와 무관한 제한값만 전달한다."""
        return CallLimits(
            timeout_seconds=self.llm_timeout_seconds,
            max_output_tokens=self.llm_max_output_tokens,
            max_input_bytes=self.llm_max_input_bytes,
            max_response_bytes=self.llm_max_response_bytes,
        )


@lru_cache(maxsize=1)
def get_settings() -> LLMSettings:
    """호출 시점에만 환경과 선택적 ``.env`` 파일을 읽는다."""

    return LLMSettings()
