"""pydantic-settings 기반 환경변수 단일 진입점. 다른 곳에서 os.environ 을 읽지 않는다.

docs/layer-rules.md 2절 · .env.example / task-01
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """`.env` 와 프로세스 환경변수를 읽는 유일한 지점."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ── 앱 ────────────────────────────────────────────────────────────
    app_env: Literal["local", "dev", "prod"] = "local"
    api_prefix: str = "/api"
    frontend_origin: str = "http://localhost:5173"

    # ── DB / Redis ───────────────────────────────────────────────────
    database_url: str = "postgresql+asyncpg://devon:devon@localhost:5432/devon"
    redis_url: str = "redis://localhost:6379/0"

    # ── 쿠키 / 세션 ──────────────────────────────────────────────────
    # DEVON JWT 전달 방식은 PENDING_FE 다. 확정 전까지 Redis 세션 쿠키만 읽는다.
    session_cookie_name: str = "devon_session"
    session_ttl_seconds: int = 1_209_600

    # ── GitHub ───────────────────────────────────────────────────────
    github_api_base: str = "https://api.github.com"
    github_timeout_seconds: float = 10.0
    # access_token_encrypted 복호화 키 (AES-GCM 256bit, base64). 평문 저장 금지.
    token_encryption_key: str = ""

    # ── 정책 · 분석 ──────────────────────────────────────────────────
    analysis_run_ttl_seconds: int = 7_200  # run_expired 판정
    repo_candidate_limit: int = 10  # 첫 batch 상한
    repo_min_size_kb: int = 50  # 룰 필터 임계값
    jd_reuse_ttl_hours: int = 24  # db-schema.md: fetched_at 기준 24시간
    jd_requirement_limit: int = 20
    readme_max_chars: int = 20_000  # 초과 시 잘라내고 partial 처리
    candidate_page_retry_after_seconds: int = 3

    # AI(L1 repo_analyze / match_score) 연결 전까지 두 step 을 건너뛴다.
    # true 로 바꾸면 app/llm_tasks 경계를 호출한다 (AI 패키지 구현 전에는 실패한다).
    analysis_ai_steps_enabled: bool = False

    # ── 정책 · 면접 ──────────────────────────────────────────────────
    max_selected_repos: int = 5
    max_ai_recommended: int = Field(default=5, description="is_selected 상한과 같아야 한다")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """프로세스 단위 싱글턴. 테스트에서는 `get_settings.cache_clear()` 로 초기화한다."""
    return Settings()
