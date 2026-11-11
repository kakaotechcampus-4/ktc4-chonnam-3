"""질문에 없는 채점 설명을 만들지 않는 v17 Plan의 순수 변환 경계."""

import importlib
import json
from copy import deepcopy
from dataclasses import asdict, replace

import pytest

from devon_ai import contracts as c


def module():
    return importlib.import_module("devon_ai.agents.director.plan_wire")


def wire():
    return {
        "persona": "hr_manager",
        "preamble": "학습 목적으로 코드를 보셨다고 했습니다.",
        "request": "본인이 맡은 역할은 무엇인가요?",
        "topic_code": "role",
        "question_contract": {
            "point_key": "role",
            "assumptions": [],
            "basis_refs": [],
            "evaluation_keys": ["contribution_clarity", "communication"],
        },
        "evidence_refs": [],
        "jd_requirement_ids": [],
        "question_type": "main",
        "parent_turn_id": None,
    }


def decode(raw):
    return module().decode_plan_question(raw, prompt_version="director_v17@pilot")


def test_source_bound_wire_builds_one_full_request_and_keeps_original_wire():
    raw = wire()
    before = deepcopy(raw)
    result = decode(raw)
    assert raw == before
    assert result.text == raw["preamble"] + " " + raw["request"]
    assert result.question_contract.purpose == raw["request"]
    assert result.question_contract.required_points == (c.RequiredPoint("role", raw["request"]),)
    assert result.question_contract.evaluation_scope == module().SOURCE_BOUND_SCOPE
    assert module().validate_source_bound_question(result) is None


def test_empty_preamble_and_exact_visible_assumptions_are_supported():
    raw = wire()
    raw["preamble"] = ""
    raw["request"] = "같은 키로 재요청한다고 가정하면 무엇을 확인하시겠어요?"
    raw["question_contract"]["assumptions"] = ["같은 키로 재요청한다고 가정하면"]
    assert decode(raw).text == raw["request"]


@pytest.mark.parametrize("change", ["purpose", "required_points", "evaluation_scope", "text"])
def test_source_bound_wire_rejects_old_free_contract_fields_and_public_text(change):
    raw = wire()
    if change == "text":
        raw[change] = "별도 질문"
    else:
        raw["question_contract"][change] = [] if change == "required_points" else "별도 설명"
    with pytest.raises(c.ContractError):
        decode(raw)


@pytest.mark.parametrize("field", ["request", "point_key", "assumption", "preamble", "missing"])
def test_source_bound_wire_rejects_invisible_assumptions_and_incomplete_requests(field):
    raw = wire()
    if field == "point_key":
        raw["question_contract"][field] = " "
    elif field == "assumption":
        raw["question_contract"]["assumptions"] = ["질문에 없는 운영 경험을 전제로 한다"]
    elif field == "missing":
        del raw["question_contract"]["evaluation_keys"]
    else:
        raw[field] = " "
    with pytest.raises(c.ContractError):
        decode(raw)


@pytest.mark.parametrize(
    "change", ["purpose", "description", "scope", "extra_point", "text", "assumption"]
)
def test_source_bound_revalidation_rejects_canonical_contract_drift(change):
    candidate = decode(wire())
    contract = candidate.question_contract
    if change == "purpose":
        contract = replace(contract, purpose=contract.purpose + "와 이유")
    elif change == "description":
        contract = replace(contract, required_points=(c.RequiredPoint("role", "역할과 이유"),))
    elif change == "scope":
        contract = replace(contract, evaluation_scope="질문에 없는 이유도 평가한다")
    elif change == "extra_point":
        contract = replace(
            contract, required_points=contract.required_points + (c.RequiredPoint("why", "이유"),)
        )
    elif change == "assumption":
        contract = replace(contract, assumptions=("질문에 없는 가정",))
    candidate = replace(
        candidate,
        question_contract=contract,
        text="request 뒤에 추가 지시" if change == "text" else candidate.text,
    )
    with pytest.raises(c.ContractError):
        module().validate_source_bound_question(candidate)


@pytest.mark.parametrize("version", ["director_v1", "director_v10@old", "director_v16@old"])
def test_old_versions_keep_public_wire_and_do_not_accept_v4(version):
    candidate = decode(wire())
    public = json.loads(json.dumps(asdict(candidate)))
    assert module().decode_plan_question(public, prompt_version=version) == candidate
    for schema in ("director-plan.v1", "director-plan.v2", "director-plan.v3"):
        assert module().plan_schema_matches_version(schema, version)
        assert not module().plan_schema_matches_version(schema, "director_v17@pilot")
    assert not module().plan_schema_matches_version("director-plan.v4", version)
    assert module().plan_schema_matches_version("director-plan.v4", "director_v17@pilot")
    with pytest.raises(c.ContractError):
        module().decode_plan_question(wire(), prompt_version=version)
