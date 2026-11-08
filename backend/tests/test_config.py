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

# 운영 연결 예시는 안전한 무설정 fallback과 구분하며, 의도한 차이만 정확히 허용한다.
OPERATIONAL_EXAMPLES: dict[str, object] = {
    "OPENAI_MODEL": "gpt-6-luna",
    "LLM_CONNECTION_SLOT": 3,
    "LLM_TASK_TIMEOUTS": {
        "repo_deep": 120,
        "answer_analysis": 120,
        "director": 120,
        "report_score": 180,
        "report": 180,
    },
    "OPENAI_MODEL_2": "gpt-6.1-terra",
    "OPENAI_MODEL_3": "gpt-6.1-sol",
    "LLM_TIMEOUT_SECONDS": 50,
    "LLM_MAX_OUTPUT_TOKENS": 128000,
    "LLM_MAX_INPUT_BYTES": 262144,
    "LLM_MAX_RESPONSE_BYTES": 67108864,
    "LLM_REASONING_EFFORT": "xhigh",
    "LLM_STREAM": True,
    "TTS_PROVIDER": "google_cloud",
    "TTS_VOICE_MAP": {
        "tech_lead": "ko-KR-Chirp3-HD-Charon",
        "domain_lead": "ko-KR-Chirp3-HD-Kore",
        "hr_manager": "ko-KR-Chirp3-HD-Aoede",
    },
    "TTS_MONTHLY_CHARACTER_LIMIT": 1000000,
}
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

    assert diff == set(OPERATIONAL_EXAMPLES), f"의도한 운영 예시와 실제 차이의 키: {sorted(diff)}"
    for key, expected in OPERATIONAL_EXAMPLES.items():
        parsed = Settings(_env_file=None, **{key.lower(): items[key]})
        assert getattr(parsed, key.lower()) == expected


def test_env_example_keeps_private_connection_values_empty() -> None:
    items = dict(_env_example_items())
    assert PRIVATE_PLACEHOLDERS <= items.keys()
    _assert_private_placeholders(items)


def test_env_example_parses_the_explicit_sol_slot_and_call_policies() -> None:
    _assert_private_placeholders(dict(_env_example_items()))
    # 실행 연결은 가짜 주소·키를 메모리에만 주입하며 실제 API는 호출하지 않는다.
    settings = Settings(
        _env_file=ENV_EXAMPLE,
        chat_proxy_url_3="https://slot-three.example.test/v1",
        proxy_token="example-fixture-key",
    )
    llm = settings.require_llm()
    assert settings.llm_connection_slot == 3
    assert llm.llm_default_model == "gpt-6.1-sol"
    for name, timeout in {
        "report": 180,
        "report_score": 180,
        "profile_summary": 50,
        "repo_deep": 120,
        "answer_analysis": 120,
        "director": 120,
    }.items():
        limits = llm.call_limits(name)
        assert limits.timeout_seconds == timeout
        assert limits.max_output_tokens == 128000
        assert limits.reasoning_effort == "xhigh"
        assert limits.stream is True
        assert limits.max_input_bytes == 262144
        assert limits.max_response_bytes == 67108864


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
