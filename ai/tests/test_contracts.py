from dataclasses import FrozenInstanceError

import pytest

from devon_ai import contracts as c


@pytest.fixture
def contract_data():
    return {
        "purpose": "캐시 선정 근거 확인",
        "required_points": [
            {"key": "reads", "description": "조회 특성"},
            {"key": "writes", "description": "수정 특성"},
            {"key": "choice", "description": "선정 이유"},
        ],
        "assumptions": [],
        "basis_refs": [],
        "evaluation_scope": "조회·수정 특성과 캐시 선정 이유",
    }


def test_contract_decodes_without_defaults_and_cannot_be_mutated(contract_data):
    result = c.decode(c.QuestionContract, contract_data)
    contract_data["required_points"][0]["key"] = "changed"
    assert result.required_points[0].key == "reads"
    assert result.assumptions == ()
    with pytest.raises(FrozenInstanceError):
        result.purpose = "다른 목적"


@pytest.mark.parametrize(
    "change",
    [
        lambda data: data.pop("purpose"),
        lambda data: data.update(purpose=None),
        lambda data: data.update(purpose=" "),
        lambda data: data.update(required_points=None),
        lambda data: data.update(required_points=[]),
        lambda data: data["required_points"].append(data["required_points"][0].copy()),
        lambda data: data.update(voice="unused"),
    ],
)
def test_contract_rejects_missing_null_empty_duplicate_and_extra_fields(contract_data, change):
    change(contract_data)
    with pytest.raises(c.ContractError):
        c.decode(c.QuestionContract, contract_data)


def test_personas_are_injected_and_all_three_are_required():
    raw = [
        {
            "persona": name,
            "question_responsibilities": ["주입한 책임"],
            "avoided_assumptions": ["주입한 금지 전제"],
        }
        for name in ("tech_lead", "hr_manager", "domain_lead")
    ]
    result = c.validate_personas(tuple(c.decode(c.Persona, item) for item in raw))
    assert result[2].persona == "domain_lead"
    assert result[0].question_responsibilities == ("주입한 책임",)
    with pytest.raises(c.ContractError):
        c.validate_personas(result[:2])
    with pytest.raises(c.ContractError):
        c.validate_personas((result[0], result[0], result[1]))


@pytest.mark.parametrize("value", ["MANAGER", "SENIOR_DEVELOPER", None, 1])
def test_persona_rejects_unknown_or_coerced_identity(value):
    with pytest.raises(c.ContractError):
        c.decode(
            c.Persona,
            {
                "persona": value,
                "question_responsibilities": ["책임"],
                "avoided_assumptions": ["전제"],
            },
        )


@pytest.fixture
def question_data(contract_data):
    return {
        "persona": "tech_lead",
        "text": "조회·수정 특성과 캐시 선정 이유는 무엇인가요?",
        "topic_code": "cache_choice",
        "question_contract": contract_data,
        "evidence_refs": ["ev-1"],
        "jd_requirement_ids": ["jd-1"],
    }


@pytest.fixture
def question_scope(contract_data):
    return {
        "review": c.QuestionReview(
            "조회·수정 특성과 캐시 선정 이유는 무엇인가요?",
            c.decode(c.QuestionContract, contract_data),
        ),
        "allowed_personas": ("tech_lead", "domain_lead"),
        "evidence_refs": frozenset({"ev-1"}),
        "basis_refs": frozenset({"source-1"}),
        "jd_requirement_ids": frozenset({"jd-1"}),
    }


def test_question_matches_independently_reviewed_requirements(question_data, question_scope):
    candidate = c.decode(c.Question, question_data)
    checked = c.validate_question(candidate, **question_scope)
    assert checked.data.text == "조회·수정 특성과 캐시 선정 이유는 무엇인가요?"
    assert tuple(point.key for point in checked.data.question_contract.required_points) == (
        "reads",
        "writes",
        "choice",
    )
    assert not isinstance(candidate, c.ContractChecked)
    with pytest.raises(TypeError):
        c.ContractChecked(candidate)


@pytest.mark.parametrize(
    "change",
    [
        lambda q: q["question_contract"]["required_points"].append(
            {"key": "ttl", "description": "질문하지 않은 TTL"}
        ),
        lambda q: q.update(text="TTL은 몇 분인가요?"),
        lambda q: q["question_contract"].update(purpose="다른 목적"),
        lambda q: q.update(persona="hr_manager"),
        lambda q: q.update(evidence_refs=["fabricated-id"]),
        lambda q: q.update(evidence_refs=["ev-1", "ev-1"]),
        lambda q: q.update(jd_requirement_ids=["other-jd"]),
        lambda q: q["question_contract"].update(basis_refs=["other-source"]),
    ],
)
def test_question_rejects_unasked_points_stale_review_and_invalid_refs(
    question_data, question_scope, change
):
    change(question_data)
    with pytest.raises(c.ContractError) as failure:
        c.validate_question(c.decode(c.Question, question_data), **question_scope)
    assert failure.value.stage == "semantic"


@pytest.mark.parametrize("field", ["question_id", "turn_id", "turn_no", "status"])
def test_question_never_accepts_model_generated_service_identifiers(question_data, field):
    question_data[field] = "model-generated"
    with pytest.raises(c.ContractError) as failure:
        c.decode(c.Question, question_data)
    assert failure.value.stage == "schema"


def test_raw_or_decoded_review_cannot_masquerade_as_trusted_review(question_data, question_scope):
    with pytest.raises(c.ContractError):
        c.validate_question(question_data, **question_scope)
    question_scope["review"] = question_data
    with pytest.raises(c.ContractError):
        c.validate_question(c.decode(c.Question, question_data), **question_scope)


def test_hr_question_accepts_empty_code_references():
    contract = c.QuestionContract(
        "자기소개", (c.RequiredPoint("intro", "자기소개"),), (), (), "자기소개 내용"
    )
    question = c.Question("hr_manager", "자기소개를 부탁드립니다", "introduction", contract, (), ())
    result = c.validate_question(
        question,
        review=c.QuestionReview(question.text, contract),
        allowed_personas=("hr_manager",),
        evidence_refs=frozenset(),
        basis_refs=frozenset(),
        jd_requirement_ids=frozenset(),
    )
    assert result.data.evidence_refs == ()


@pytest.fixture
def analysis_data():
    return {
        "evaluation_status": "evaluated",
        "sufficiency": "partial",
        "covered_points": [
            {"key": "reads", "answer_quotes": ["조회가 많아서"]},
            {"key": "choice", "answer_quotes": ["DB 부하를 줄이려고"]},
        ],
        "missing_points": ["writes"],
        "technical_assessment": {
            "explanation": "캐시 선정 목적을 설명함",
            "answer_quotes": ["캐시했습니다"],
            "evidence_refs": [],
            "limitations": ["구현 근거 미확인"],
        },
        "contribution_scope": "unknown",
        "contribution_quotes": [],
        "claim_checks": [],
        "needs_verification": False,
        "verification_requests": [],
        "limitations": [],
    }


def check_analysis(data, question, scope):
    checked_question = c.validate_question(c.decode(c.Question, question), **scope)
    return c.validate_analysis(
        c.decode(c.AnswerAnalysis, data),
        question=checked_question,
        answer_text="조회가 많아서 DB 부하를 줄이려고 캐시했습니다",
        evidence_refs=frozenset({"ev-1"}),
        allowed_locations=frozenset({("repo-1", "sha-1", "src/cache.py")}),
    )


def test_partial_answer_preserves_three_axes_and_only_actual_missing_point(
    analysis_data, question_data, question_scope
):
    result = check_analysis(analysis_data, question_data, question_scope).data
    assert result.sufficiency == "partial"
    assert result.missing_points == ("writes",)
    assert result.covered_points[0].answer_quotes == ("조회가 많아서",)
    assert result.contribution_scope == "unknown"
    assert result.technical_assessment.limitations == ("구현 근거 미확인",)


@pytest.mark.parametrize(
    "change",
    [
        lambda a: a.update(missing_points=["ttl"]),
        lambda a: a.update(missing_points=["writes", "writes"]),
        lambda a: a["covered_points"][0].update(answer_quotes=["존재하지 않는 답변"]),
        lambda a: a["covered_points"].append(a["covered_points"][0].copy()),
        lambda a: a.update(sufficiency="sufficient"),
        lambda a: a.update(evaluation_status="not_evaluable"),
        lambda a: a.update(contribution_scope="self"),
        lambda a: a.update(needs_verification=True),
        lambda a: a["technical_assessment"].update(evidence_refs=["unknown-evidence"]),
    ],
)
def test_analysis_rejects_unasked_missing_points_false_quotes_and_inconsistent_results(
    analysis_data, question_data, question_scope, change
):
    change(analysis_data)
    with pytest.raises(c.ContractError) as failure:
        check_analysis(analysis_data, question_data, question_scope)
    assert failure.value.stage == "semantic"


def test_not_evaluable_requires_reason_and_does_not_manufacture_missing_points(
    analysis_data, question_data, question_scope
):
    analysis_data.update(
        evaluation_status="not_evaluable",
        sufficiency=None,
        covered_points=[],
        missing_points=[],
        limitations=["질문 전제 오류"],
    )
    assert check_analysis(analysis_data, question_data, question_scope).data.sufficiency is None
    analysis_data["limitations"] = []
    with pytest.raises(c.ContractError):
        check_analysis(analysis_data, question_data, question_scope)


@pytest.mark.parametrize(
    "field,value",
    [
        ("sufficiency", "high"),
        ("contribution_scope", None),
        ("evaluation_status", "done"),
        ("needs_verification", 1),
    ],
)
def test_analysis_schema_rejects_new_enum_null_and_boolean_coercion(analysis_data, field, value):
    analysis_data[field] = value
    with pytest.raises(c.ContractError) as failure:
        c.decode(c.AnswerAnalysis, analysis_data)
    assert failure.value.stage == "schema"


def test_analysis_cannot_consume_raw_question(analysis_data, question_data):
    with pytest.raises(c.ContractError):
        c.validate_analysis(
            c.decode(c.AnswerAnalysis, analysis_data),
            question=c.decode(c.Question, question_data),
            answer_text="답변",
            evidence_refs=frozenset(),
            allowed_locations=frozenset(),
        )
