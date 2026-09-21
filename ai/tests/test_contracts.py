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
