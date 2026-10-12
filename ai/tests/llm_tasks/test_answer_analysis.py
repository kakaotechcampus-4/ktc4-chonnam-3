import json
from dataclasses import replace

import pytest

from devon_ai import contracts as c

ANALYSIS_FIELDS = {
    "evaluation_status",
    "sufficiency",
    "covered_points",
    "missing_points",
    "technical_assessment",
    "contribution_scope",
    "claim_checks",
    "needs_verification",
    "verification_requests",
    "limitations",
}


def test_partial_answer_returns_checked_analysis_scoped_to_the_question(kit, run):
    provider = kit.Provider(kit.analysis_output())
    result = run(provider)
    assert result.succeeded
    data = result.data.data
    assert data.sufficiency == "partial"
    assert tuple(point.key for point in data.covered_points) == ("read_pattern", "cache_purpose")
    # 질문하지 않은 TTL은 누락이나 감점 사유가 아니며 수정 특성만 남는다.
    assert data.missing_points == ("write_pattern",)
    assert "TTL" not in json.dumps(c.to_data(result.data), ensure_ascii=False)
    assert result.attempts == (kit.metadata(),)
    request = provider.requests[0]
    assert request.prompt.task_name == "answer_analysis"
    assert request.schema_name == "AnswerAnalysis"
    assert set(request.output_schema["properties"]) == ANALYSIS_FIELDS
    assert request.max_attempts == 2


def test_request_carries_the_question_scope_and_answer_but_no_persona_proxy(kit, run):
    provider = kit.Provider(kit.analysis_output())
    run(provider)
    payload = provider.requests[0].payload
    assert payload["answer"] == {"turn_id": "turn-3", "text": kit.ANSWER}
    assert payload["question"]["question_contract"]["purpose"] == "조회·수정 특성과 캐시 선정 이유"
    assert [turn["turn_id"] for turn in payload["history"]] == ["turn-1", "turn-2"]
    # 평가 기준은 Persona별로 달라지지 않으므로 모델 입력에 Persona를 넣지 않는다.
    dumped = json.dumps(payload, ensure_ascii=False)
    assert "persona" not in dumped and "tech_lead" not in dumped and "hr_manager" not in dumped


def test_model_may_only_return_the_ten_analysis_fields(kit, run):
    output = kit.analysis_output()
    output["score"] = 80
    result = run(kit.Provider(output))
    assert result.data is None and result.failure.stage == "schema"


@pytest.mark.parametrize(
    "case",
    [
        "other_turn",
        "answered_turn",
        "other_contract",
        "empty_answer",
        "unchecked_question",
        "wrong_prompt",
        "unknown_location_repository",
        "location_other_ref",
        "evidence_other_ref",
    ],
)
def test_invalid_input_is_rejected_before_any_model_call(kit, run, case):
    provider = kit.Provider(kit.analysis_output())
    options: dict[str, object] = {}
    answer = kit.ANSWER
    if case == "other_turn":
        options["turn_id"] = "turn-2"
    elif case == "answered_turn":
        history = kit.make_context().history
        options["context"] = kit.make_context(
            history=history + (replace(history[0], turn_id="turn-3"),)
        )
    elif case == "other_contract":
        options["context"] = kit.make_context(
            current_question_contract=replace(kit.make_contract(), purpose="다른 목적")
        )
    elif case == "empty_answer":
        answer = "  \n"
    elif case == "unchecked_question":
        options["question"] = kit.checked_question().data
    elif case == "wrong_prompt":
        options["prompt"] = replace(kit.PROMPT, task_name="director")
    elif case == "unknown_location_repository":
        options["allowed_locations"] = frozenset({("repo-9", kit.REF, "a.py")})
    elif case == "location_other_ref":
        options["allowed_locations"] = frozenset({("repo-1", kit.OTHER_REF, "a.py")})
    else:
        evidence = c.Evidence("ev-1", "repo-1", kit.OTHER_REF, "file", "a.py", None, "x", "grep")
        options["context"] = kit.make_context(evidence=(evidence,))
    result = run(provider, answer=answer, **options)
    assert result.data is None and result.failure.error_code == "answer_analysis_input_invalid"
    assert result.attempts == () and provider.requests == []


def test_no_remaining_budget_is_a_budget_failure_without_a_call(kit, run):
    provider = kit.Provider(kit.analysis_output())
    context = kit.make_context(limits=c.ContextLimits(0, 0, "fixture"))
    result = run(provider, context=context)
    assert result.failure.stage == "budget" and provider.requests == []


def test_a_model_call_that_skips_the_validator_cannot_return_unchecked_analysis(kit, run):
    other = c.validate_analysis(
        c.decode(c.AnswerAnalysis, kit.analysis_output()),
        question=kit.checked_question(),
        answer_text=kit.ANSWER,
        evidence_refs=frozenset(),
        allowed_locations=frozenset(),
    )

    async def skips_validator(request, validator):
        return c.ModelResult(other, None, (kit.metadata(),))

    # 같은 질문에 대한 검증이라도 이 답변 원문을 기준으로 다시 확인해 통과 값만 반환한다.
    result = run(skips_validator, answer="전혀 다른 답변입니다.")
    assert result.data is None
    assert result.failure.error_code == "answer_analysis_invalid"
    assert result.attempts == (kit.metadata(),)
