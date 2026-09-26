"""pydantic-settings 기반 환경변수 단일 진입점. 다른 곳에서 os.environ 을 읽지 않는다.

docs/layer-rules.md 2절 · .env.example / task-01
"""

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

AppEnv = Literal["local", "dev", "prod"]
CookieSameSite = Literal["lax", "strict", "none"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]


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
    openai_api_key: str = ""
    llm_default_model: str = "gpt-5.6-luna"
    llm_timeout_seconds: int = 60
    llm_max_retries: int = 1

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
