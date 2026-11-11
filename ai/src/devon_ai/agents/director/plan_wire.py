"""버전별 Plan 원시 표현을 저장 가능한 동일 Question으로 복원한다."""

from dataclasses import MISSING, fields
from typing import cast

from devon_ai import contracts as c
from devon_ai.agents.director.capabilities import prompt_capabilities

SOURCE_BOUND_PLAN_SCHEMA = "director-plan.v4"
SOURCE_BOUND_SCOPE = (
    "표시된 질문에서 직접 요구한 답만 평가한다. 배경의 재설명이나 질문하지 않은 이유·관계·"
    "조치를 추가로 요구하지 않으며, 제공된 자료와 실제 답변으로 확인할 수 없는 사실은 "
    "미확인으로 둔다."
)
_LEGACY_PLAN_SCHEMAS = frozenset({"director-plan.v1", "director-plan.v2", "director-plan.v3"})


def _plan_object(
    raw: object, expected: set[str], name: str, optional: frozenset[str] = frozenset()
) -> dict[str, object]:
    if type(raw) is not dict or not expected - optional <= set(raw) <= expected:
        raise c.ContractError("schema", name)
    return cast(dict[str, object], raw)


def plan_schema_matches_version(schema_version: str, prompt_version: str) -> bool:
    """v17은 v4만 사용하고, 과거 버전의 기존 v1~v3 허용은 소급 강화하지 않는다."""
    if prompt_capabilities(prompt_version).source_bound_contract:
        return schema_version == SOURCE_BOUND_PLAN_SCHEMA
    return schema_version in _LEGACY_PLAN_SCHEMAS


def _legacy_question(raw: object) -> c.Question:
    question = _plan_object(
        raw,
        {item.name for item in fields(c.Question)},
        "Question",
        frozenset(item.name for item in fields(c.Question) if item.default is not MISSING),
    )
    contract = _plan_object(
        question["question_contract"],
        {item.name for item in fields(c.QuestionContract)},
        "QuestionContract",
        frozenset(item.name for item in fields(c.QuestionContract) if item.default is not MISSING),
    )
    for name, expected in (
        ("required_points", {item.name for item in fields(c.RequiredPoint)}),
        ("basis_refs", {item.name for item in fields(c.BasisRef)}),
    ):
        entries = contract[name]
        if type(entries) is not list:
            raise c.ContractError("schema", name)
        for item in entries:
            _plan_object(item, expected, name)
    return c.decode(c.Question, question)


def validate_source_bound_question(candidate: c.Question) -> None:
    """문장 의미를 판정하지 않고 코드가 구성한 계약의 원문 결합만 재검증한다."""
    if type(candidate) is not c.Question:
        raise c.ContractError("schema", "source-bound question")
    candidate.__post_init__()
    contract = candidate.question_contract
    if len(contract.required_points) != 1:
        raise c.ContractError("semantic", "source-bound required point")
    request = contract.required_points[0].description
    if contract.purpose != request or contract.evaluation_scope != SOURCE_BOUND_SCOPE:
        raise c.ContractError("semantic", "source-bound contract")
    if candidate.text != request:
        suffix = " " + request
        if not candidate.text.endswith(suffix) or not candidate.text[: -len(suffix)].strip():
            raise c.ContractError("semantic", "source-bound request suffix")
    if any(assumption not in candidate.text for assumption in contract.assumptions):
        raise c.ContractError("semantic", "source-bound assumption excerpt")


def decode_plan_question(raw: object, *, prompt_version: str) -> c.Question:
    """v4의 자유 채점 설명은 받지 않는다. 기존 Question 표현 파서는 유지한다."""
    if not prompt_capabilities(prompt_version).source_bound_contract:
        return _legacy_question(raw)
    question = _plan_object(
        raw,
        {item.name for item in fields(c.Question)} - {"text"} | {"preamble", "request"},
        "source-bound question wire",
    )
    contract = _plan_object(
        question["question_contract"],
        {"point_key", "assumptions", "basis_refs", "evaluation_keys"},
        "source-bound contract wire",
    )
    preamble, request = question["preamble"], question["request"]
    if (
        type(preamble) is not str
        or (preamble != "" and not preamble.strip())
        or type(request) is not str
        or not request.strip()
    ):
        raise c.ContractError("schema", "source-bound question segments")
    public = {
        key: value
        for key, value in question.items()
        if key not in {"preamble", "request", "question_contract"}
    }
    public["text"] = preamble + " " + request if preamble else request
    public["question_contract"] = {
        "purpose": request,
        "required_points": [{"key": contract["point_key"], "description": request}],
        "assumptions": contract["assumptions"],
        "basis_refs": contract["basis_refs"],
        "evaluation_scope": SOURCE_BOUND_SCOPE,
        "evaluation_keys": contract["evaluation_keys"],
    }
    candidate = c.decode_strict(c.Question, public)
    validate_source_bound_question(candidate)
    return candidate
