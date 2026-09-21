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
