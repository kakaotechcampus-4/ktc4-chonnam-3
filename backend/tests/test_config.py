""".env.example 과 Settings 필드가 어긋나지 않는지 본다.

task-01 — 한쪽만 바꾸면 기본값이 조용히 갈라지므로 테스트로 묶는다.
"""

import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings

ENV_EXAMPLE = Path(__file__).resolve().parents[1] / ".env.example"
ENV_LINE = re.compile(r"^(?P<key>[A-Z][A-Z0-9_]*)=(?P<value>[^#]*)")

# .env.example 에만 있고 Settings 에 없어도 되는 키 (스프린트2 예약 등).
UNMAPPED_KEYS: set[str] = set()

# 기본 모델 선택만 공유 예제에 명시한다. 공급자별 개발 예산은 별도 선택 프로필이다.
EXAMPLE_OVERRIDES = {"OPENAI_MODEL"}
DEVELOPMENT_PROFILE = ENV_EXAMPLE.parent / "config/ai-development.env.example"
PRIVATE_PLACEHOLDERS = {
    "GITHUB_CLIENT_ID",
    "GITHUB_CLIENT_SECRET",
    "TOKEN_ENCRYPTION_KEY",
    "OPENAI_API_KEY",
    "PROXY_TOKEN",
    "CHAT_PROXY_URL",
    "CHAT_PROXY_URL_2",
    "CHAT_PROXY_URL_3",
    "TTS_API_KEY",
    "TTS_ACCESS_TOKEN",
    "TAVILY_API_KEY",
    "VISION_BASE_URL",
    "VISION_API_KEY",
    "STT_BASE_URL",
    "STT_API_KEY",
}


def _assert_private_placeholders(items: dict[str, str]) -> None:
    # 잘못 들어온 비공개 값이 테스트 실패 메시지에 다시 노출되지 않게 키만 보고한다.
    unsafe = {key for key in PRIVATE_PLACEHOLDERS if items.get(key)}
    assert not unsafe, f"예제의 비공개 입력은 빈 값이어야 합니다: {sorted(unsafe)}"


def _env_example_items() -> list[tuple[str, str]]:
    """.env.example 에서 주석 처리되지 않은 (키, 값) 을 순서대로 모은다. 값의 인라인 주석은 뗀다."""
    items: list[tuple[str, str]] = []
    for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        matched = ENV_LINE.match(line.strip())
        if matched:
            items.append((matched.group("key"), matched.group("value").strip()))
    return items


def _env_example_keys() -> set[str]:
    """.env.example 에서 주석 처리되지 않은 키 이름을 모은다."""
    return {key for key, _ in _env_example_items()}


def test_env_example_keys_all_exist_in_settings() -> None:
    missing = {
        k for k in _env_example_keys() - UNMAPPED_KEYS if k.lower() not in Settings.model_fields
    }

    assert not missing, f".env.example 에만 있는 키: {sorted(missing)}"


def test_env_example_has_no_duplicate_keys() -> None:
    """같은 키가 두 번 있으면 뒤의 값이 조용히 이긴다."""
    keys = [key for key, _ in _env_example_items()]
    duplicated = sorted({key for key in keys if keys.count(key) > 1})

    assert not duplicated, f".env.example 에 중복된 키: {duplicated}"


def test_env_example_defaults_match_settings() -> None:
    """명시한 운영 예시 외의 값은 Settings fallback과 같아야 한다."""
    items = dict(_env_example_items())
    _assert_private_placeholders(items)
    settings = Settings(_env_file=None)
    diff = {
        key
        for key, value in _env_example_items()
        if value
        and key not in UNMAPPED_KEYS
        and key.lower() in Settings.model_fields
        # 환경변수의 JSON/배분·숫자 형식을 실제 Settings와 같은 경계에서 해석한다.
        and getattr(Settings(_env_file=None, **{key.lower(): value}), key.lower())
        != getattr(settings, key.lower())
    }

    assert diff <= EXAMPLE_OVERRIDES, f"공유 예제에 개발 프로필 값이 섞였습니다: {sorted(diff)}"


def test_env_example_keeps_private_connection_values_empty() -> None:
    items = dict(_env_example_items())
    assert PRIVATE_PLACEHOLDERS <= items.keys()
    _assert_private_placeholders(items)


@pytest.mark.parametrize("slot,model", [(None, "gpt-6-luna"), (3, "gpt-6.1-sol")])
def test_selected_development_profile_preserves_luna_and_explicit_sol_slot(slot, model) -> None:
    _assert_private_placeholders(dict(_env_example_items()))
    # 실행 연결은 가짜 주소·키를 메모리에만 주입하며 실제 API는 호출하지 않는다.
    overrides = {"llm_connection_slot": slot} if slot is not None else {}
    settings = Settings(
        _env_file=(ENV_EXAMPLE, DEVELOPMENT_PROFILE),
        chat_proxy_url="https://slot-one.example.test/v1",
        chat_proxy_url_3="https://slot-three.example.test/v1",
        proxy_token="example-fixture-key",
        **overrides,
    )
    llm = settings.require_llm()
    assert settings.llm_connection_slot == (slot or 1)
    assert llm.llm_default_model == model
    # 프로필의 선택값을 읽되 특정 수치 자체를 전역 기본값으로 강제하지 않는다.
    for name, timeout in llm.llm_task_timeouts.items():
        assert llm.call_limits(name).timeout_seconds == timeout
    assert llm.call_limits().max_output_tokens == settings.llm_max_output_tokens
    assert llm.call_limits().max_response_bytes == settings.llm_max_response_bytes


def test_shared_example_requires_explicit_provider_limits():
    settings = Settings(_env_file=ENV_EXAMPLE)
    assert settings.llm_max_output_tokens is None
    assert settings.tts_provider is None
    with pytest.raises(ValidationError):
        settings.require_llm()


def test_settings_load_without_env_file() -> None:
    """.env 가 없는 환경(CI·컨테이너)에서도 기본값으로 뜬다."""
    settings = Settings(_env_file=None)

    assert settings.app_env == "local"
    assert settings.api_prefix == "/api"
    assert settings.llm_default_model == "gpt-5.6-luna"


def test_persona_turn_quota_parses_env_string() -> None:
    settings = Settings(_env_file=None, persona_turn_quota="tech_lead:6,domain_lead:2,hr_manager:1")

    assert settings.persona_turn_quota == {"tech_lead": 6, "domain_lead": 2, "hr_manager": 1}


@pytest.mark.parametrize(
    "quota",
    [
        {"tech_lead": 5, "domain_lead": 3, "hr_manager": 1},
        {"tech_lead": 6, "domain_lead": 1, "hr_manager": 2},
        {"tech_lead": 6, "domain_lead": 2},
        {"tech_lead": 6, "domain_lead": 2, "hr_manager": 1, "extra": 0},
    ],
    ids=["shifted-tech-count", "shifted-domain-count", "missing-role", "extra-role"],
)
def test_persona_turn_quota_rejects_non_fixed_allocation(quota: dict[str, int]) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, persona_turn_quota=quota)


@pytest.mark.parametrize("turns", [True, 1.0, "1"], ids=["boolean", "float", "string"])
def test_persona_turn_quota_rejects_non_integer_mapping_counts(turns: object) -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            persona_turn_quota={"tech_lead": 6, "domain_lead": 2, "hr_manager": turns},
        )


@pytest.mark.parametrize(
    "quota",
    [
        "tech_lead:5,domain_lead:3,hr_manager:1",
        "tech_lead:6,domain_lead:2,hr_manager:1,hr_manager:1",
        "tech_lead:6,domain_lead:2,hr_manager:1,",
        "tech_lead:6,domain_lead:2,hr_manager:true",
        "tech_lead:6,domain_lead:2,hr_manager:1.0",
        "tech_lead:6,domain_lead:2,hr_manager",
    ],
    ids=["wrong-counts", "duplicate-role", "empty-pair", "boolean", "float", "missing-count"],
)
def test_persona_turn_quota_rejects_invalid_env_strings(
    monkeypatch: pytest.MonkeyPatch, quota: str
) -> None:
    monkeypatch.setenv("PERSONA_TURN_QUOTA", quota)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_interview_allocation_loads_fixed_values_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PERSONA_TURN_QUOTA", " hr_manager:1, tech_lead:6, domain_lead:2 ")
    monkeypatch.setenv("INTERVIEW_MAX_TURNS", "9")

    settings = Settings(_env_file=None)

    assert settings.persona_turn_quota == {"tech_lead": 6, "domain_lead": 2, "hr_manager": 1}
    assert settings.interview_max_turns == 9


@pytest.mark.parametrize("turns", [8, 10, True, 9.0, "9.0", "10"])
def test_interview_max_turns_rejects_non_fixed_or_coerced_values(turns: object) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, interview_max_turns=turns)


def test_persona_turn_quota_sums_to_max_turns() -> None:
    """배분 합이 최대 턴 수와 다르면 면접 설계가 어긋난다 (backend/CLAUDE.md)."""
    settings = Settings(_env_file=None)

    assert sum(settings.persona_turn_quota.values()) == settings.interview_max_turns


def test_max_ai_recommended_does_not_exceed_selectable_repos() -> None:
    """추천 수가 선택 상한보다 크면 채택률 지표가 구조적으로 망가진다 (.env.example 주석)."""
    settings = Settings(_env_file=None)

    assert settings.max_ai_recommended <= settings.max_selected_repos
