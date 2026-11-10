"""pydantic-settings 기반 환경변수 단일 진입점. 다른 곳에서 os.environ 을 읽지 않는다.

docs/layer-rules.md 2절 · .env.example / task-01
"""

import base64
import binascii
import json
import math
from collections.abc import Mapping
from functools import lru_cache
from typing import TYPE_CHECKING, Annotated, Literal
from urllib.parse import urlsplit

from devon_ai.contracts import CallLimits
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

if TYPE_CHECKING:
    from app.integrations.search.tavily import TavilySettings
    from app.integrations.tts.google import TTSSettings
    from app.integrations.vision.elice import EliceVisionSettings

AppEnv = Literal["local", "dev", "prod"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]

# 공통 ADR 0008 고정 배분 결정에 따라 정상 면접의 persona 배정과 총 턴을 고정한다.
FIXED_PERSONA_TURN_QUOTA = {"tech_lead": 6, "domain_lead": 2, "hr_manager": 1}
INTERVIEW_MAX_TURNS = 9


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


def _task_timeout_values(value: object) -> dict[str, float]:
    if isinstance(value, str):
        value = json.loads(value)
    allowed = {
        "repo_shallow",
        "repo_deep",
        "domain_category",
        "doc_claims",
        "director",
        "answer_analysis",
        "report",
        "report_score",
        "profile_summary",
        "claim_code",
        "jd_extract_image",
    }
    if not isinstance(value, dict) or any(key not in allowed for key in value):
        raise ValueError("Unknown LLM task timeout")
    result: dict[str, float] = {}
    for key, number in value.items():
        if (
            isinstance(number, bool)
            or not isinstance(number, (int, float))
            or not math.isfinite(number)
            or number <= 0
        ):
            raise ValueError("Task timeouts must be positive finite numbers")
        result[str(key)] = float(number)
    return result


TaskTimeouts = Annotated[dict[str, float], BeforeValidator(_task_timeout_values)]


class LLMSettings(BaseModel):
    """이미 읽은 설정에서 실제 LLM 호출에 필요한 값만 검증한다.

    환경을 다시 읽거나 누락된 실행 상한을 채우지 않는다. 미설정이면 호출 전에 실패한다.
    """

    model_config = ConfigDict(hide_input_in_errors=True)

    openai_api_key: SecretStr = Field(min_length=1)
    llm_base_url: str = Field(default="https://api.openai.com/v1", repr=False)
    llm_default_model: str = Field(min_length=1)
    llm_timeout_seconds: LLMTimeout = Field(gt=0, allow_inf_nan=False)
    llm_max_output_tokens: LLMInteger = Field(gt=0)
    llm_max_input_bytes: LLMInteger = Field(gt=0)
    llm_max_response_bytes: LLMInteger = Field(gt=0)
    llm_reasoning_effort: Literal["none", "minimal", "low", "medium", "high", "xhigh"] | None = None
    llm_stream: bool = False

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

    @field_validator("llm_base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        # urlsplit이 제어문자를 제거하기 전에 거절하고 오류에 접속 주소를 포함하지 않는다.
        invalid = "LLM base URL must be HTTPS without credentials, query, or fragment"
        if any(char.isspace() or ord(char) < 32 or 127 <= ord(char) <= 159 for char in value):
            raise ValueError(invalid)
        if any(char in value for char in ("\\", "?", "#")):
            raise ValueError(invalid)
        try:
            parsed = urlsplit(value)
            if (
                parsed.scheme != "https"
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
            ):
                raise ValueError(invalid)
            # 포트의 형식·범위 검증은 실제 속성 접근 때 수행된다.
            _ = parsed.port
        except ValueError:
            raise ValueError(invalid) from None
        # 프록시 namespace와 API 버전 경로를 유지하며 끝의 구분자만 제거한다.
        return parsed.geturl().rstrip("/")

    llm_task_timeouts: TaskTimeouts = Field(default_factory=dict)

    def call_limits(self, task_name: str | None = None) -> CallLimits:
        """AI에는 환경변수나 비밀키 대신 공급자와 무관한 제한값만 전달한다."""
        return CallLimits(
            timeout_seconds=self.llm_task_timeouts.get(task_name or "", self.llm_timeout_seconds),
            max_output_tokens=self.llm_max_output_tokens,
            max_input_bytes=self.llm_max_input_bytes,
            max_response_bytes=self.llm_max_response_bytes,
            reasoning_effort=self.llm_reasoning_effort,
            stream=self.llm_stream,
        )


class STTSettings(BaseModel):
    """이미 읽은 설정에서 실제 STT 호출에 필요한 값만 검증한다.

    미설정이면 앱은 기동하고 호출 전에 실패한다. 오류에는 입력값(주소·키)을 싣지 않는다.
    """

    model_config = ConfigDict(hide_input_in_errors=True)

    stt_provider: str = Field(min_length=1)
    stt_base_url: str = Field(repr=False)
    stt_api_key: SecretStr = Field(min_length=1)
    stt_model: str = Field(min_length=1)
    stt_language: str = Field(min_length=1)
    stt_timeout_seconds: LLMTimeout = Field(gt=0, allow_inf_nan=False)
    stt_max_response_bytes: LLMInteger = Field(default=1048576, gt=0)
    stt_max_audio_bytes: LLMInteger = Field(gt=0)
    stt_min_audio_bytes: LLMInteger = Field(ge=0)
    stt_hallucination_phrases: tuple[str, ...]
    stt_hallucination_max_seconds: LLMTimeout = Field(gt=0, allow_inf_nan=False)

    @field_validator("stt_provider", "stt_model", "stt_language")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("STT setting must not be blank")
        return value.strip()

    @field_validator("stt_api_key")
    @classmethod
    def _api_key_not_blank(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError("stt_api_key must not be blank")
        return value

    @field_validator("stt_base_url")
    @classmethod
    def _validate_base_url(cls, value: str) -> str:
        invalid = "STT base URL must be HTTPS without credentials, query, or fragment"
        if any(char.isspace() or ord(char) < 32 or 127 <= ord(char) <= 159 for char in value):
            raise ValueError(invalid)
        if any(char in value for char in ("\\", "?", "#")):
            raise ValueError(invalid)
        try:
            parsed = urlsplit(value)
            if (
                parsed.scheme != "https"
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
            ):
                raise ValueError(invalid)
            _ = parsed.port
        except ValueError:
            raise ValueError(invalid) from None
        # 전사 클라이언트가 /v1/audio/transcriptions를 붙이므로 끝의 버전만 한 번 제거한다.
        return parsed.geturl().rstrip("/").removesuffix("/v1")


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
    log_json: bool = False

    # ── DB / Redis ──
    database_url: str = Field(
        default="postgresql+asyncpg://devon:devon@localhost:5432/devon", repr=False
    )
    redis_url: str = Field(default="redis://localhost:6379/0", repr=False)

    # ── 쿠키 / 세션 ──
    session_cookie_name: str = "devon_session"
    session_ttl_seconds: int = Field(default=1209600, gt=0)
    cookie_secure: bool = False
    cookie_samesite: Literal["lax"] = "lax"

    # ── GitHub OAuth ──
    github_client_id: str = ""
    github_client_secret: SecretStr = SecretStr("")
    github_login_scope: str = "read:user"
    github_link_scope: str = "read:user"
    github_redirect_uri: str = "http://localhost:5173/auth/github/callback"
    token_encryption_key: SecretStr = SecretStr("")

    # ── LLM ──
    # 모델명을 코드 상수로 두지 않는다. 아래는 seed 가 읽는 기본값이고
    # 실제 사용값은 prompt_versions.model 등 DB 에 저장한다 (backend/CLAUDE.md).
    openai_api_key: SecretStr | None = None
    proxy_token: SecretStr | None = None
    chat_proxy_url: str | None = Field(default=None, repr=False)
    openai_model: str | None = None
    # 기존 연결을 보존하면서 주소와 모델을 같은 슬롯에서 함께 선택한다.
    chat_proxy_url_2: str | None = Field(default=None, repr=False)
    openai_model_2: str | None = None
    chat_proxy_url_3: str | None = Field(default=None, repr=False)
    openai_model_3: str | None = None
    llm_connection_slot: LLMInteger = Field(default=1, ge=1, le=3)
    llm_task_timeouts: Annotated[TaskTimeouts, NoDecode] = Field(default_factory=dict)
    llm_default_model: str | None = "gpt-5.6-luna"
    # 비어 있는 LLM 설정이 health 등 일반 앱 기동을 막지 않도록 호출 시점에 필수 검증한다.
    llm_timeout_seconds: LLMTimeout | None = None
    llm_max_output_tokens: LLMInteger | None = None
    llm_max_input_bytes: LLMInteger | None = None
    llm_max_response_bytes: LLMInteger | None = None
    llm_reasoning_effort: Literal["none", "minimal", "low", "medium", "high", "xhigh"] | None = None
    llm_stream: bool = False
    # 공통 호출 계약의 자동 재시도 1회(총 시도 2회)이며 변경 가능한 호출 예산이 아니다.
    llm_max_retries: LLMInteger = Field(default=1, ge=1, le=1)
    jd_max_images: LLMInteger = Field(default=4, ge=1, le=8)
    jd_max_total_image_bytes: LLMInteger = Field(default=8388608, gt=0)
    jd_image_timeout_seconds: LLMTimeout = Field(default=30.0, gt=0, allow_inf_nan=False)
    # 다운로드별 대기와 별개로 전체 이미지·Vision 순차 처리를 제한한다.
    jd_image_total_timeout_seconds: LLMTimeout = Field(default=360.0, gt=0, allow_inf_nan=False)

    # 선택 공급자의 키가 없어도 앱은 기동한다. 기능을 호출하는 경계에서만 검증한다.
    tavily_api_key: SecretStr | None = None
    tavily_timeout_seconds: LLMTimeout = Field(default=20.0, gt=0)
    tavily_max_response_bytes: LLMInteger = Field(default=1048576, gt=0)
    tavily_max_content_chars: LLMInteger = Field(default=24000, gt=0)
    tavily_max_results: LLMInteger = Field(default=5, ge=1, le=20)
    tavily_max_calls: LLMInteger = Field(default=4, ge=1)
    tavily_max_credits: LLMInteger = Field(default=4, ge=1)
    external_sources_cache_seconds: LLMInteger = Field(default=3600, gt=0)
    external_max_calls_per_interview: LLMInteger = Field(default=8, gt=0)
    external_max_credits_per_interview: LLMInteger = Field(default=8, gt=0)

    vision_base_url: str | None = Field(default=None, repr=False)
    vision_api_key: SecretStr | None = None
    # 기존 MLAPI 콘솔 변수명도 Settings에서 읽고, 전용 Vision 설정이 없을 때만 사용한다.
    helpy_vision_document_proxy_url: str | None = Field(default=None, repr=False)
    vision_model: str = "eliceai/helpy-document-vision"
    vision_timeout_seconds: LLMTimeout = Field(default=60.0, gt=0)
    vision_max_file_bytes: LLMInteger = Field(default=20971520, gt=0)
    vision_max_response_bytes: LLMInteger = Field(default=8388608, gt=0)
    vision_max_polls: LLMInteger = Field(default=12, gt=0)
    vision_poll_interval_seconds: LLMTimeout = Field(default=1.0, gt=0)
    vision_job_path_template: str = "/v1/jobs/{job_id}"
    vision_pdf_layout: bool = False
    documents_max_source_chars: LLMInteger = Field(default=262144, gt=0)

    tts_provider: str | None = None
    tts_api_key: SecretStr | None = None
    tts_access_token: SecretStr | None = None
    tts_voice_map: Annotated[dict[str, str], NoDecode] = Field(default_factory=dict)
    tts_language_code: str = "ko-KR"
    tts_timeout_seconds: LLMTimeout = Field(default=20.0, gt=0)
    tts_max_text_bytes: LLMInteger = Field(default=4500, gt=0)
    tts_max_audio_bytes: LLMInteger = Field(default=2097152, gt=0)
    tts_cache_ttl_seconds: LLMInteger = Field(default=3600, gt=0)
    # 무료 잔여량을 확인해 명시적으로 초기화하기 전에는 합성을 시작하지 않는다.
    tts_monthly_character_limit: LLMInteger | None = Field(default=None, gt=0, le=1000000)
    tts_budget_project: str | None = None

    # ── STT (MLAPI Whisper) ──
    # 비어 있어도 앱은 기동하고, 답변 전사 호출 전에 require_stt()가 검증한다.
    # 크기·시간 상한은 MLAPI 쪽 한도를 확인하지 못해 잡은 보수적 기본값이며 설정으로 조정한다.
    stt_provider: str | None = None
    stt_base_url: str | None = Field(default=None, repr=False)
    stt_api_key: SecretStr | None = None
    # 기존 MLAPI 콘솔 변수는 전용 STT 주소가 없을 때만 사용한다.
    whisper_large_v3_proxy_url: str | None = Field(default=None, repr=False)
    stt_model: str | None = "whisper-large-v3"
    # MLAPI는 언어 코드(ko)가 아니라 이름(korean)을 받는다.
    stt_language: str | None = "korean"
    stt_timeout_seconds: LLMTimeout = Field(default=30.0, gt=0, allow_inf_nan=False)
    stt_max_response_bytes: LLMInteger = Field(default=1048576, gt=0)
    stt_max_audio_bytes: LLMInteger = Field(default=10485760, gt=0)
    # 이보다 짧은 오디오는 STT를 호출하지 않고 빈 전사로 본다. webm/opus는 초당 약 4KB(0007)라
    # 기본값은 1초 안팎이며 실측 후 조정한다. 0이면 빈 오디오만 거른다.
    stt_min_audio_bytes: LLMInteger = Field(default=4096, ge=0)
    # 무음에도 200과 함께 오는 환각 문구(실측: "감사합니다."). 전사 전체가 이 문구와 같고 오디오가
    # 아래 길이 이하일 때만 빈 전사로 본다. 쉼표로 구분하며 빈 값이면 필터를 끈다.
    stt_hallucination_phrases: Annotated[tuple[str, ...], NoDecode] = ("감사합니다",)
    stt_hallucination_max_seconds: LLMTimeout = Field(default=15.0, gt=0, allow_inf_nan=False)
    # 답변 오디오 수신 규칙(0007). 180초는 FE·서버 공통 상한, 여유는 FE 타이머·마지막 조각 지연분.
    answer_audio_max_seconds: LLMTimeout = Field(default=180.0, gt=0, allow_inf_nan=False)
    answer_audio_grace_seconds: LLMTimeout = Field(default=5.0, ge=0, allow_inf_nan=False)
    # 오디오가 이 시간 동안 오지 않으면 미완료 오디오를 버린다(0007 제안 10초).
    answer_audio_idle_timeout_seconds: LLMTimeout = Field(default=10.0, gt=0, allow_inf_nan=False)

    # ── 정책 · 분석 ──
    analysis_run_ttl_seconds: int = 7200
    max_upload_bytes_cover_letter: int = 10485760
    max_upload_bytes_portfolio: int = 20971520
    # 파일 byte 제한과 별개인 보관 텍스트 상한. URL 목록은 축약 전에 확보한다.
    documents_max_text_chars: int = Field(default=50000, gt=0)
    repo_candidate_limit: int = 10
    repo_min_size_kb: int = 50
    jd_reuse_ttl_days: int = 7
    jd_requirement_limit: int = 20
    claim_limit: int = 10

    # ── 정책 · 면접 ──
    # 진행 중 근거 조회의 유한 상한이며 품질·지연의 실측 목표는 아니다.
    director_evidence_max_requests: LLMInteger = Field(default=12, gt=0, le=64)
    director_evidence_max_files: LLMInteger = Field(default=2, gt=0, le=16)
    director_evidence_timeout_seconds: LLMTimeout = Field(default=8.0, gt=0, allow_inf_nan=False)

    max_active_interviews_per_user: int = 1
    max_selected_repos: int = 5
    max_ai_recommended: int = 5
    interview_max_turns: int = INTERVIEW_MAX_TURNS
    interview_duration_seconds: int = 1200
    # 원래 enqueue 와 겹치지 않도록 이 시간 이상 preparing 인 면접만 reaper 가 재등록한다.
    interview_prep_reaper_min_age_seconds: int = Field(default=60, gt=0)
    # 진행 중 근거 재조회는 작은 기존 상한을 유지한다.
    director_evidence_max_response_bytes: LLMInteger = Field(default=131072, gt=0)
    director_evidence_max_total_bytes: LLMInteger = Field(default=262144, gt=0)
    # 준비는 고정 tree의 구조 목록도 읽는다. 원문 입력량·후속 Tool 예산과 분리한다.
    # 공개 서비스 tree 실측 1111590 bytes/4209항목을 수용하되 유한 상한을 유지한다.
    director_prepare_max_response_bytes: LLMInteger = Field(default=2097152, gt=0)
    director_prepare_max_total_bytes: LLMInteger = Field(default=8388608, gt=0)
    director_prepare_max_source_bytes: LLMInteger = Field(default=262144, gt=0)
    director_prepare_max_entries: LLMInteger = Field(default=8192, gt=0, le=8192)
    director_prepare_max_depth: LLMInteger = Field(default=12, gt=0, le=20)
    director_prepare_max_requests: LLMInteger = Field(default=32, gt=0, le=128)
    director_prepare_max_files: LLMInteger = Field(default=8, gt=0, le=16)
    director_prepare_max_file_bytes: LLMInteger = Field(default=32768, gt=0)
    # 선택한 공급자의 schema 제한에 맞추며 원문·모델 입력 byte 예산과 별도로 검사한다.
    repository_selection_max_enum_values: LLMInteger = Field(default=900, gt=0)
    repository_selection_max_enum_characters: LLMInteger = Field(default=14000, gt=0)
    # 선정 모델의 대기는 제외한 원문 HTTP 처리 전체의 시간 예산이다.
    director_prepare_timeout_seconds: LLMTimeout = Field(default=30.0, gt=0, allow_inf_nan=False)
    # NoDecode — pydantic-settings 가 dict 를 JSON 으로 먼저 파싱하지 않게 한다.
    #            .env 는 `tech_lead:6,...` 형식이라 아래 validator 가 직접 해석한다.
    persona_turn_quota: Annotated[dict[str, int], NoDecode] = FIXED_PERSONA_TURN_QUOTA

    @field_validator(
        "openai_api_key",
        "proxy_token",
        "chat_proxy_url",
        "openai_model",
        "chat_proxy_url_2",
        "openai_model_2",
        "chat_proxy_url_3",
        "openai_model_3",
        "llm_default_model",
        "llm_timeout_seconds",
        "llm_max_output_tokens",
        "llm_max_input_bytes",
        "llm_max_response_bytes",
        "llm_reasoning_effort",
        mode="before",
    )
    @classmethod
    def _empty_llm_value_is_unset(cls, value: object) -> object:
        return None if isinstance(value, str) and not value.strip() else value

    def require_llm(self) -> LLMSettings:
        """캐시된 설정만 검증하며 비밀키와 네 실행 상한이 준비되지 않으면 실패한다."""
        if self.llm_connection_slot != 1:
            suffix = str(self.llm_connection_slot)
            base_url = getattr(self, "chat_proxy_url_" + suffix)
            model = getattr(self, "openai_model_" + suffix)
            if base_url is None or model is None or self.proxy_token is None:
                raise ValueError("Selected LLM slot requires its URL, model, and PROXY_TOKEN")
            values = self.model_dump(include=set(LLMSettings.model_fields))
            values.update(
                openai_api_key=self.proxy_token, llm_base_url=base_url, llm_default_model=model
            )
            return LLMSettings.model_validate(values)
        if (self.proxy_token is None) != (self.chat_proxy_url is None):
            raise ValueError("PROXY_TOKEN and CHAT_PROXY_URL must be configured together")
        values = self.model_dump(include=set(LLMSettings.model_fields))
        if self.chat_proxy_url is not None:
            values["openai_api_key"] = self.proxy_token
            values["llm_base_url"] = self.chat_proxy_url
        # OPENAI_MODEL을 기본 모델보다 우선하되 원본 설정과 DB prompt 모델은 변경하지 않는다.
        if self.openai_model is not None:
            values["llm_default_model"] = self.openai_model
        return LLMSettings.model_validate(values)

    @field_validator(
        "stt_provider",
        "stt_base_url",
        "stt_api_key",
        "whisper_large_v3_proxy_url",
        "stt_model",
        "stt_language",
        mode="before",
    )
    @classmethod
    def _empty_stt_value_is_unset(cls, value: object) -> object:
        return None if isinstance(value, str) and not value.strip() else value

    @field_validator("stt_hallucination_phrases", mode="before")
    @classmethod
    def _parse_hallucination_phrases(cls, value: object) -> object:
        if isinstance(value, str):
            return tuple(item.strip() for item in value.split(",") if item.strip())
        return value

    def require_stt(self) -> STTSettings:
        """캐시된 설정만 검증하며 주소·키·모델이 준비되지 않으면 실패한다."""
        values = self.model_dump(include=set(STTSettings.model_fields))
        if self.stt_base_url is None and self.whisper_large_v3_proxy_url is not None:
            values["stt_base_url"] = self.whisper_large_v3_proxy_url
            if self.stt_api_key is None:
                # 공통 키는 MLAPI 호환 주소에만 적용하고 명시한 별도 주소에는 전달하지 않는다.
                values["stt_api_key"] = self.proxy_token
        return STTSettings.model_validate(values)

    @field_validator(
        "tts_provider",
        "tts_api_key",
        "tts_access_token",
        "tts_budget_project",
        "tts_monthly_character_limit",
        "vision_base_url",
        "vision_api_key",
        "helpy_vision_document_proxy_url",
        "tavily_api_key",
        mode="before",
    )
    @classmethod
    def _empty_optional_provider_value_is_unset(cls, value: object) -> object:
        # 명시 전용 주소의 우선순위는 유지하고 빈 선택값만 미설정으로 취급한다.
        raw = value.get_secret_value() if isinstance(value, SecretStr) else value
        return None if isinstance(raw, str) and not raw.strip() else value

    @field_validator("tts_voice_map", mode="before")
    @classmethod
    def _parse_voice_map(cls, value: object) -> object:
        if isinstance(value, str):
            if not value.strip():
                return {}
            try:
                return json.loads(value)
            except ValueError:
                raise ValueError("TTS voice map must be a JSON object") from None
        return value

    def require_tavily(self) -> "TavilySettings":
        from app.integrations.search.tavily import TavilySettings

        if self.tavily_api_key is None or not self.tavily_api_key.get_secret_value().strip():
            raise ValueError("Tavily credentials are not configured")
        return TavilySettings(
            api_key=self.tavily_api_key,
            timeout_seconds=self.tavily_timeout_seconds,
            max_response_bytes=self.tavily_max_response_bytes,
            max_content_chars=self.tavily_max_content_chars,
            max_results=self.tavily_max_results,
        )

    def require_vision(self) -> "EliceVisionSettings":
        from app.integrations.vision.elice import EliceVisionSettings

        base_url = self.vision_base_url or self.helpy_vision_document_proxy_url
        api_key = self.vision_api_key
        if api_key is None and not self.vision_base_url and self.helpy_vision_document_proxy_url:
            # 공통 토큰을 임의의 명시 엔드포인트로 보내지 않고 MLAPI 호환 경로에만 적용한다.
            api_key = self.proxy_token
        if not base_url or api_key is None:
            raise ValueError("Vision endpoint and credentials are not configured")
        return EliceVisionSettings(
            base_url=base_url,
            api_key=api_key,
            model=self.vision_model,
            timeout_seconds=self.vision_timeout_seconds,
            max_file_bytes=self.vision_max_file_bytes,
            max_response_bytes=self.vision_max_response_bytes,
            max_polls=self.vision_max_polls,
            poll_interval_seconds=self.vision_poll_interval_seconds,
            job_path_template=self.vision_job_path_template,
        )

    def require_tts(self) -> "TTSSettings":
        from app.integrations.tts.google import TTSSettings

        if not self.tts_provider:
            raise ValueError("TTS provider is not configured")
        return TTSSettings(
            provider=self.tts_provider,
            voice_map=self.tts_voice_map,
            api_key=self.tts_api_key,
            access_token=self.tts_access_token,
            language_code=self.tts_language_code,
            timeout_seconds=self.tts_timeout_seconds,
            max_text_bytes=self.tts_max_text_bytes,
            max_audio_bytes=self.tts_max_audio_bytes,
            cache_ttl_seconds=self.tts_cache_ttl_seconds,
            monthly_character_limit=self.tts_monthly_character_limit,
            budget_project=self.tts_budget_project,
        )

    def call_limits(self, task_name: str | None = None) -> CallLimits:
        """LLM 설정을 먼저 검증한 뒤 AI 호출에 전달할 상한을 만든다."""
        return self.require_llm().call_limits(task_name)

    @field_validator("persona_turn_quota", mode="before")
    @classmethod
    def _parse_persona_turn_quota(cls, value: object) -> object:
        """환경 문자열을 해석하고 타입 변환 전에 고정 배정을 검증한다."""
        if isinstance(value, str):
            quota: dict[str, int] = {}
            for pair in value.split(","):
                persona, separator, turns = pair.strip().partition(":")
                persona = persona.strip()
                if not separator or persona in quota:
                    raise ValueError("persona_turn_quota requires unique role:count pairs")
                quota[persona] = int(turns)
            value = quota
        if (
            not isinstance(value, Mapping)
            or any(type(turns) is not int for turns in value.values())
            or value != FIXED_PERSONA_TURN_QUOTA
        ):
            raise ValueError("persona_turn_quota must be tech_lead:6,domain_lead:2,hr_manager:1")
        return value

    @field_validator("interview_max_turns", mode="before")
    @classmethod
    def _validate_interview_max_turns(cls, value: object) -> object:
        if isinstance(value, str):
            value = int(value)
        if type(value) is not int or value != INTERVIEW_MAX_TURNS:
            raise ValueError("interview_max_turns must be the integer 9")
        return value

    @field_validator("analysis_run_ttl_seconds", "repo_candidate_limit")
    @classmethod
    def _positive_analysis_limit(cls, value: int) -> int:
        # 문서 업로드 설정과 독립적으로 기존 분석 상한의 양수 조건을 유지한다.
        if value <= 0:
            raise ValueError("Analysis limits must be greater than zero")
        return value

    @property
    def is_prod(self) -> bool:
        """prod 환경 여부. 쿠키 secure 강제나 문서 노출 차단 판단에 쓴다."""
        return self.app_env == "prod"

    @property
    def github_link_redirect_uri(self) -> str:
        return self.github_redirect_uri

    def validate_auth(self) -> None:
        """인증 설정만 기동 시 검증하고, LLM 설정은 실제 호출 시 별도로 검증한다."""
        origin = urlsplit(self.frontend_origin)
        callback = urlsplit(self.github_redirect_uri)
        if (
            origin.scheme not in {"http", "https"}
            or not origin.netloc
            or origin.username is not None
            or origin.password is not None
            or origin.path not in {"", "/"}
            or origin.query
            or origin.fragment
            or (callback.scheme, callback.netloc) != (origin.scheme, origin.netloc)
            or callback.path != "/auth/github/callback"
            or callback.query
            or callback.fragment
        ):
            raise ValueError("OAuth callback must be FRONTEND_ORIGIN/auth/github/callback")
        if self.is_prod and (origin.scheme != "https" or not self.cookie_secure):
            raise ValueError("Production requires HTTPS and Secure session cookies")
        if self.api_prefix != "/api" or self.session_cookie_name != "devon_session":
            raise ValueError("Sprint 1 requires /api and the devon_session cookie")
        if self.github_login_scope != "read:user" or self.github_link_scope != "read:user":
            raise ValueError("Sprint 1 GitHub scope must be read:user")
        if not self.github_client_id or not self.github_client_secret.get_secret_value():
            raise ValueError("GitHub OAuth client credentials must be configured")
        try:
            key = base64.b64decode(self.token_encryption_key.get_secret_value(), validate=True)
        except (ValueError, binascii.Error):
            raise ValueError("TOKEN_ENCRYPTION_KEY must be a base64-encoded 32-byte key") from None
        if len(key) != 32:
            raise ValueError("TOKEN_ENCRYPTION_KEY must be a base64-encoded 32-byte key")


@lru_cache
def get_settings() -> Settings:
    """Settings 싱글턴. 프로세스 수명 동안 .env 를 한 번만 읽는다."""
    return Settings()
