"""pydantic-settings 기반 환경변수 단일 진입점. 다른 곳에서 os.environ 을 읽지 않는다.

docs/layer-rules.md 2절 · .env.example / task-01
"""

from functools import lru_cache
from typing import Annotated, Literal

from devon_ai.contracts import CallLimits
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

AppEnv = Literal["local", "dev", "prod"]
CookieSameSite = Literal["lax", "strict", "none"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]


def _reject_boolean_timeout(value: object) -> object:
    if isinstance(value, bool):
        raise ValueError("llm_timeout_seconds must be a number")
    return value


def _reject_non_integer_limit(value: object) -> object:
    if isinstance(value, (bool, float)):
        raise ValueError("LLM integer limits must be integers")
    return value


# 설정을 읽을 때 잘못된 숫자 타입이 먼저 변환되면 호출 시 검증에서 구분할 수 없다.
LLMTimeout = Annotated[float, BeforeValidator(_reject_boolean_timeout)]
LLMInteger = Annotated[int, BeforeValidator(_reject_non_integer_limit)]


class LLMSettings(BaseModel):
    """이미 읽은 설정에서 실제 LLM 호출에 필요한 값만 검증한다.

    환경을 다시 읽거나 누락된 실행 상한을 채우지 않는다. 미설정이면 호출 전에 실패한다.
    """

    model_config = ConfigDict(hide_input_in_errors=True)

    openai_api_key: SecretStr = Field(min_length=1)
    llm_default_model: str = Field(min_length=1)
    llm_timeout_seconds: LLMTimeout = Field(gt=0, allow_inf_nan=False)
    llm_max_output_tokens: LLMInteger = Field(gt=0)
    llm_max_input_bytes: LLMInteger = Field(gt=0)
    llm_max_response_bytes: LLMInteger = Field(gt=0)

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

    def call_limits(self) -> CallLimits:
        """AI에는 환경변수나 비밀키 대신 공급자와 무관한 제한값만 전달한다."""
        return CallLimits(
            timeout_seconds=self.llm_timeout_seconds,
            max_output_tokens=self.llm_max_output_tokens,
            max_input_bytes=self.llm_max_input_bytes,
            max_response_bytes=self.llm_max_response_bytes,
        )


class Settings(BaseSettings):
    """.env 를 읽는 설정 단일 진입점.

    필드명은 snake_case 이고 환경변수는 대문자다 (pydantic-settings 가 대소문자를 맞춘다).
    기본값은 .env.example 과 동일하게 유지한다 — 한쪽만 바꾸지 않는다.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        # SecretStr 변환 전의 입력도 검증 오류 문자열에 노출되지 않게 한다.
        hide_input_in_errors=True,
    )

    # ── 앱 ──
    app_env: AppEnv = "local"
    api_prefix: str = "/api"
    frontend_origin: str = "http://localhost:5173"
    log_level: LogLevel = "INFO"

    # ── DB / Redis ──
    database_url: str = "postgresql+asyncpg://devon:devon@localhost:5432/devon"
    redis_url: str = "redis://localhost:6379/0"

    # ── 쿠키 / 세션 ──
    session_cookie_name: str = "devon_session"
    session_ttl_seconds: int = 1209600
    cookie_secure: bool = False
    cookie_samesite: CookieSameSite = "lax"

    # ── DEVON 자체 JWT ──
    # payload 에 GitHub access token 을 넣지 않는다 (docs/db-schema.md).
    auth_cookie_name: str = "accessToken"
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    jwt_expires_seconds: int = 1209600

    # ── GitHub OAuth ──
    github_client_id: str = ""
    github_client_secret: str = ""
    github_login_scope: str = "read:user"
    github_link_scope: str = "read:user"
    github_redirect_uri: str = "http://localhost:8000/api/auth/github/callback"
    token_encryption_key: str = ""

    # ── LLM ──
    # 모델명을 코드 상수로 두지 않는다. 아래는 seed 가 읽는 기본값이고
    # 실제 사용값은 prompt_versions.model 등 DB 에 저장한다 (backend/CLAUDE.md).
    openai_api_key: SecretStr | None = None
    llm_default_model: str | None = "gpt-5.6-luna"
    # 비어 있는 LLM 설정이 health 등 일반 앱 기동을 막지 않도록 호출 시점에 필수 검증한다.
    llm_timeout_seconds: LLMTimeout | None = None
    llm_max_output_tokens: LLMInteger | None = None
    llm_max_input_bytes: LLMInteger | None = None
    llm_max_response_bytes: LLMInteger | None = None
    # ADR 0010의 자동 재시도 1회(총 시도 2회)를 표시하며 변경 가능한 호출 예산이 아니다.
    llm_max_retries: LLMInteger = Field(default=1, ge=1, le=1)

    # ── 정책 · 분석 ──
    analysis_run_ttl_seconds: int = 7200
    max_upload_bytes_cover_letter: int = 10485760
    max_upload_bytes_portfolio: int = 20971520
    repo_candidate_limit: int = 10
    repo_min_size_kb: int = 50
    jd_reuse_ttl_days: int = 7
    jd_requirement_limit: int = 20
    claim_limit: int = 10

    # ── 정책 · 면접 ──
    max_active_interviews_per_user: int = 1
    max_selected_repos: int = 5
    max_ai_recommended: int = 5
    interview_max_turns: int = 9
    interview_duration_seconds: int = 1200
    # NoDecode — pydantic-settings 가 dict 를 JSON 으로 먼저 파싱하지 않게 한다.
    #            .env 는 `tech_lead:6,...` 형식이라 아래 validator 가 직접 해석한다.
    persona_turn_quota: Annotated[dict[str, int], NoDecode] = {
        "tech_lead": 6,
        "domain_lead": 2,
        "hr_manager": 1,
    }

    @field_validator(
        "openai_api_key",
        "llm_default_model",
        "llm_timeout_seconds",
        "llm_max_output_tokens",
        "llm_max_input_bytes",
        "llm_max_response_bytes",
        mode="before",
    )
    @classmethod
    def _empty_llm_value_is_unset(cls, value: object) -> object:
        return None if isinstance(value, str) and not value.strip() else value

    def require_llm(self) -> LLMSettings:
        """캐시된 설정만 검증하며 비밀키와 네 실행 상한이 준비되지 않으면 실패한다."""
        return LLMSettings.model_validate(self, from_attributes=True)

    def call_limits(self) -> CallLimits:
        """LLM 설정을 먼저 검증한 뒤 AI 호출에 전달할 상한을 만든다."""
        return self.require_llm().call_limits()

    @field_validator("persona_turn_quota", mode="before")
    @classmethod
    def _parse_persona_turn_quota(cls, value: object) -> object:
        """`tech_lead:6,domain_lead:2,hr_manager:1` 형태를 dict 로 바꾼다.

        입력: env 문자열 또는 이미 dict 인 값. 출력: dict[str, int] 로 해석 가능한 값.
        """
        if not isinstance(value, str):
            return value
        quota: dict[str, int] = {}
        for pair in value.split(","):
            pair = pair.strip()
            if not pair:
                continue
            persona, _, turns = pair.partition(":")
            quota[persona.strip()] = int(turns)
        return quota

    @property
    def is_prod(self) -> bool:
        """prod 환경 여부. 쿠키 secure 강제나 문서 노출 차단 판단에 쓴다."""
        return self.app_env == "prod"


@lru_cache
def get_settings() -> Settings:
    """Settings 싱글턴. 프로세스 수명 동안 .env 를 한 번만 읽는다."""
    return Settings()
