import json
from dataclasses import asdict, replace

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


def jd_question(kit, reference_kind):
    basis = (c.BasisRef("jd_requirement", "jd-1"),) if reference_kind != "question" else ()
    ids = ("jd-1",) if reference_kind != "basis" else ()
    contract = c.QuestionContract(
        "공고의 메시징 요구사항과 구현의 연결",
        (c.RequiredPoint("jd_alignment", "공고 조건과 본인 구현의 연결"),),
        (),
        basis,
        "질문이 참조한 공고 원문의 조건",
    )
    question = replace(
        kit.checked_question().data,
        text="본인의 메시징 설계가 해당 공고의 요구사항을 어떻게 충족하나요?",
        question_contract=contract,
        jd_requirement_ids=ids,
    )
    return c.validate_question(
        question,
        review=c.QuestionReview(question.text, contract),
        allowed_personas=("tech_lead",),
        evidence_refs=frozenset(),
        basis_refs=frozenset(basis),
        jd_requirement_ids=frozenset(ids),
    )


@pytest.mark.parametrize("reference_kind", ["question", "basis", "both"])
def test_referenced_jd_source_reaches_the_model_and_changes_the_payload(kit, run, reference_kind):
    question = jd_question(kit, reference_kind)
    payloads = []
    answer = "Kafka로 이벤트를 발행합니다."
    for source in (
        "Kafka 기반 비동기 이벤트 처리가 필요합니다.",
        "RabbitMQ 메시징 경험이 필요합니다.",
    ):
        requirement = c.JDRequirement("jd-1", source, "required", "requirements", ())
        context = kit.make_context(
            current_question_contract=question.data.question_contract,
            jd_requirements=(
                requirement,
                c.JDRequirement(
                    "jd-unrelated", "질문에서 참조하지 않은 조건", "preferred", "requirements", ()
                ),
            ),
        )
        output = kit.analysis_output(
            covered_points=[{"key": "jd_alignment", "answer_quotes": [answer]}],
            missing_points=[],
            sufficiency="sufficient",
            technical_assessment={
                "explanation": "조건과의 부합은 제공된 JD 원문을 확인해야 한다.",
                "answer_quotes": [answer],
                "evidence_refs": [],
                "limitations": ["이 테스트는 실제 모델의 비교 판단을 검증하지 않는다."],
            },
        )
        provider = kit.Provider(output)
        assert run(provider, context=context, question=question, answer=answer).succeeded
        payload = provider.requests[0].payload
        assert payload["question"]["jd_requirement_ids"] == list(question.data.jd_requirement_ids)
        assert payload["jd_requirements"] == [asdict(requirement)]
        payloads.append(payload)
    assert payloads[0] != payloads[1]


@pytest.mark.parametrize("reference_kind", ["question", "basis", "both"])
def test_missing_referenced_jd_is_rejected_before_model_call(kit, run, reference_kind):
    question = jd_question(kit, reference_kind)
    context = kit.make_context(current_question_contract=question.data.question_contract)
    provider = kit.Provider(kit.analysis_output())
    result = run(provider, context=context, question=question)
    assert result.failure.error_code == "answer_analysis_input_invalid"
    assert result.failure.stage == "semantic"
    assert result.attempts == () and provider.requests == []


def test_duplicate_jd_id_cannot_choose_an_ambiguous_source(kit, run):
    question = jd_question(kit, "both")
    context = kit.make_context(
        current_question_contract=question.data.question_contract,
        jd_requirements=(
            c.JDRequirement("jd-1", "Kafka 경험", "required", "requirements", ()),
            c.JDRequirement("jd-1", "RabbitMQ 경험", "required", "requirements", ()),
        ),
    )
    provider = kit.Provider(kit.analysis_output())
    result = run(provider, context=context, question=question)
    assert result.failure.error_code == "answer_analysis_input_invalid"
    assert result.failure.stage == "semantic"
    assert result.attempts == () and provider.requests == []


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
