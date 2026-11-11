"""후보 문장과 계약에 결합된 독립 검토 응답을 검증한다."""

from devon_ai import contracts as c
from devon_ai.agents.director.agent import _object_schema
from devon_ai.agents.director.capabilities import prompt_capabilities

LEGACY_REVIEW_SCHEMA = "director-review.v1"
POINT_REVIEW_SCHEMA = "director-review.v2"
STABLE_POINT_REVIEW_SCHEMA = "director-review.v3"
SUPPORTED_REVIEW_SCHEMAS = frozenset(
    {LEGACY_REVIEW_SCHEMA, POINT_REVIEW_SCHEMA, STABLE_POINT_REVIEW_SCHEMA}
)
REVIEW_CHECKS = (
    "plan_valid",
    "context_valid",
    "wording_valid",
    "contract_matches",
    "safe_alternative",
)
_COVERAGE_STATUSES = ("asked", "premise_only", "not_asked", "unclear")


def review_schema_version(prompt_version: str) -> str:
    """실행·저장 이력·진단이 같은 배포의 검토 형식을 선택한다."""
    capabilities = prompt_capabilities(prompt_version)
    if capabilities.stable_point_review:
        return STABLE_POINT_REVIEW_SCHEMA
    return POINT_REVIEW_SCHEMA if capabilities.required_point_review else LEGACY_REVIEW_SCHEMA


def review_schema(
    candidate: c.Question | None = None, *, stable: bool = False
) -> dict[str, object]:
    properties: dict[str, object] = {
        **{key: {"type": "boolean"} for key in REVIEW_CHECKS},
        "reason_summary": {"type": "string"},
    }
    if candidate is not None:
        fields: dict[str, object] = {
            "status": {"enum": list(_COVERAGE_STATUSES)},
            "question_excerpt": {"type": ["string", "null"]},
        }
        coverage = _object_schema(fields)
        properties["point_coverage"] = (
            {
                "type": "array",
                "items": _object_schema({"key": {"type": "string"}, **fields}),
            }
            if stable
            else _object_schema(
                {point.key: coverage for point in candidate.question_contract.required_points}
            )
        )
    return _object_schema(properties)


def _unasked_points(raw: object, candidate: c.Question, *, stable: bool = False) -> tuple[str, ...]:
    points = candidate.question_contract.required_points
    if stable:
        # 자유 키를 schema에 넣지 않되, 중복·누락·추가 키는 기존과 같이 승인하지 않는다.
        if type(raw) is not list:
            raise c.ContractError("schema", "review point coverage array")
        mapped = {}
        for item in raw:
            if type(item) is not dict or set(item) != {"key", "status", "question_excerpt"}:
                raise c.ContractError("schema", "review point coverage fields")
            key = item["key"]
            if type(key) is not str or key in mapped:
                raise c.ContractError("schema", "review point coverage keys")
            mapped[key] = {"status": item["status"], "question_excerpt": item["question_excerpt"]}
        raw = mapped
    if type(raw) is not dict or set(raw) != {point.key for point in points}:
        raise c.ContractError("schema", "review point coverage keys")
    unasked = []
    for point in points:
        item = raw[point.key]
        if type(item) is not dict or set(item) != {"status", "question_excerpt"}:
            raise c.ContractError("schema", "review point coverage fields")
        status, excerpt = item["status"], item["question_excerpt"]
        if type(status) is not str or status not in _COVERAGE_STATUSES:
            raise c.ContractError("schema", "review point coverage status")
        if excerpt is not None and (
            type(excerpt) is not str or not excerpt.strip() or excerpt not in candidate.text
        ):
            raise c.ContractError("schema", "review question excerpt")
        if status == "asked" and excerpt is None:
            raise c.ContractError("schema", "review question excerpt")
        if status != "asked":
            unasked.append(point.key)
    return tuple(unasked)


def assess_review(
    raw: object, candidate: c.Question, schema_version: str
) -> c.QuestionReview | c.CandidateRecovery:
    """형식 검증과 모델의 의미 판정을 결합하고 후보 계약은 수정하지 않는다."""
    fields = {*REVIEW_CHECKS, "reason_summary"}
    if schema_version in {POINT_REVIEW_SCHEMA, STABLE_POINT_REVIEW_SCHEMA}:
        fields.add("point_coverage")
    elif schema_version != LEGACY_REVIEW_SCHEMA:
        raise c.ContractError("schema", "DirectorReview version")
    if type(raw) is not dict or set(raw) != fields:
        raise c.ContractError("schema", "DirectorReview")
    if any(type(raw[key]) is not bool for key in REVIEW_CHECKS):
        raise c.ContractError("schema", "review checks")
    reason = raw["reason_summary"]
    if type(reason) is not str or not reason.strip():
        raise c.ContractError("schema", "review reason")
    unasked = (
        _unasked_points(
            raw["point_coverage"], candidate, stable=schema_version == STABLE_POINT_REVIEW_SCHEMA
        )
        if schema_version in {POINT_REVIEW_SCHEMA, STABLE_POINT_REVIEW_SCHEMA}
        else ()
    )
    if all(raw[key] for key in REVIEW_CHECKS[:-1]) and not unasked:
        return c.QuestionReview(candidate.text, candidate.question_contract)
    if not raw["safe_alternative"]:
        return c.CandidateRecovery("no_valid_candidate", reason)
    if not raw["plan_valid"] or not raw["context_valid"]:
        return c.CandidateRecovery("replan", reason)
    if unasked:
        reason = "질문에서 직접 묻는 근거를 확인하지 못한 필수점: " + ", ".join(unasked)
    return c.CandidateRecovery("rewrite", reason)
