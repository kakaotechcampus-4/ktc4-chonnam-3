"""profile_summary 집계·역할 요약 검증. 실제 LLM 은 호출하지 않는다. task-16 / ADR 0016·0019"""

import uuid

import pytest
from devon_ai import contracts as c

from app.llm_tasks import profile_summary as ps

A, B, C = (uuid.UUID(int=n) for n in (1, 2, 3))


def _ratios(result):
    return {item["name"]: item["ratio"] for item in result}


def test_equal_weight_python_and_java_split_fifty_fifty():
    result = ps.aggregate_languages({A: {"Python": 9_000_000}, B: {"Java": 10}})
    assert _ratios(result) == {"Java": 50.0, "Python": 50.0}


def test_mixed_repos_average_by_repo_not_by_code_size():
    # A: Python 80 / JS 20, B: JS 100 → Python 40 / JS 60 (ADR 0016 예시)
    result = ps.aggregate_languages({A: {"Python": 800, "JavaScript": 200}, B: {"JavaScript": 1}})
    assert _ratios(result) == {"JavaScript": 60.0, "Python": 40.0}
    assert [item["name"] for item in result] == ["JavaScript", "Python"]


def test_absent_language_counts_as_zero_without_shrinking_denominator():
    result = ps.aggregate_languages({A: {"Python": 1}, B: {"Python": 1}, C: {"Go": 1}})
    assert _ratios(result) == {"Python": 66.667, "Go": 33.333}


def test_repo_count_is_independent_of_interview_count():
    # 같은 repo 가 여러 번 들어와도 id 중복 제거 후 한 번만 집계한다.
    ids = ps.based_repo_ids([B, A, B, A, A])
    assert ids == [A, B]
    langs = {A: {"Python": 1}, B: {"Java": 1}}
    assert _ratios(ps.aggregate_languages({i: langs[i] for i in ids})) == {
        "Java": 50.0,
        "Python": 50.0,
    }


@pytest.mark.parametrize("bad", [None, {}, {"Python": 0}, {"Python": -1}, {"Python": True}])
def test_missing_language_data_fails_instead_of_zero_filling(bad):
    with pytest.raises(ps.LanguageDataMissingError):
        ps.aggregate_languages({A: {"Python": 1}, B: bad})


def test_no_repositories_fails():
    with pytest.raises(ps.LanguageDataMissingError):
        ps.aggregate_languages({})


def test_based_repo_ids_sorted_key_is_stable_for_any_input_order():
    assert ps.based_repo_ids([C, A, B]) == ps.based_repo_ids([B, C, A]) == [A, B, C]


def test_project_types_order_by_repo_count_then_name_and_dedupe_within_repo():
    result = ps.aggregate_project_types(
        {A: ["web", "web", "cli"], B: ["web", " "], C: ["cli", "api"]}
    )
    assert result == ["cli", "web", "api"]


@pytest.mark.parametrize(
    "raw",
    [None, "text", {}, {"role_summary": ""}, {"role_summary": "  "}, {"role_summary": 3}]
    + [{"role_summary": "x", "languages": []}, {"role_summary": "가" * 501}],
)
def test_role_summary_rejects_empty_malformed_or_extra_fields(raw):
    with pytest.raises(ps.RoleSummaryInvalidError):
        ps.validate_role_summary(raw, [])


def test_role_summary_rejects_unsupported_absolute_claim_but_allows_stated_one():
    raw = {"role_summary": "결제 모듈을 전담해 개발했다고 설명했습니다."}
    with pytest.raises(ps.RoleSummaryInvalidError):
        ps.validate_role_summary(raw, ["저는 API 를 만들었습니다."])
    assert ps.validate_role_summary(raw, ["결제 모듈은 제가 전담했습니다."]) == (
        "결제 모듈을 전담해 개발했다고 설명했습니다."
    )


def _limits():
    return c.CallLimits(
        timeout_seconds=5, max_output_tokens=100, max_input_bytes=1000, max_response_bytes=1000
    )


def _prompt():
    return c.PromptSpec(task_name="profile_summary", version="v1", model="m", template="t")


def _attempt():
    return c.AttemptMetadata(
        attempt=1,
        provider="p",
        model="m",
        prompt_version="v1",
        schema_version="1",
        latency_ms=1,
        input_tokens=None,
        output_tokens=None,
    )


async def test_generate_returns_validated_text_and_requests_only_role_summary():
    seen = []

    async def model_call(request, validator):
        seen.append(request)
        data = validator({"role_summary": " 요약 "})
        return c.ModelResult(data=data, failure=None, attempts=(_attempt(),))

    text = await ps.generate_role_summary(
        {"x": 1}, prompt=_prompt(), limits=_limits(), model_call=model_call, statements=[]
    )
    assert text == "요약"
    assert seen[0].output_schema["required"] == ["role_summary"]
    assert seen[0].output_schema["additionalProperties"] is False


async def test_generate_validator_reports_contract_error_for_retry():
    async def model_call(request, validator):
        with pytest.raises(c.ContractError):
            validator({"role_summary": ""})
        failure = c.CallFailure(stage="semantic", error_code="llm_failed", reason_summary="x")
        return c.ModelResult(data=None, failure=failure, attempts=(_attempt(),))

    with pytest.raises(ps.RoleSummaryCallError):
        await ps.generate_role_summary(
            {}, prompt=_prompt(), limits=_limits(), model_call=model_call, statements=[]
        )
