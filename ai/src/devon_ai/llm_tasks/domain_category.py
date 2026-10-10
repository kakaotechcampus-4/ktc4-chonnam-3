"""공고 도메인 category 판정. 결정은 spec/ai/decisions/0022-domain-category-llm.md를 따른다.

prompt 로드·provider I/O·`postings.domain_category` 저장은 BE 책임이다. 이 모듈은 요청 생성과
응답 검증, 근거 인용 확인만 맡는다.
"""

from dataclasses import asdict, dataclass
from typing import Literal, get_args

from devon_ai import contracts as c

DomainCategory = Literal["finance", "game", "travel", "shopping", "medical", "mobility", "etc"]
CATEGORIES: tuple[DomainCategory, ...] = get_args(DomainCategory)


@dataclass(frozen=True)
class DomainAnswer:
    category: DomainCategory
    evidence: str


@dataclass(frozen=True)
class DomainDecision:
    """저장할 category와 기록용 호출 정보. 호출이 실패해도 category는 항상 7종 중 하나다."""

    category: DomainCategory
    # 근거 확인을 통과해 채택한 인용. `etc`이거나 근거가 원문에 없으면 None.
    evidence: str | None
    failure: c.CallFailure | None
    attempts: tuple[c.AttemptMetadata, ...]


def _output_schema() -> dict[str, object]:
    return {
        "type": "object",
        "properties": {
            "category": {"type": "string", "enum": list(CATEGORIES)},
            "evidence": {"type": "string"},
        },
        "required": ["category", "evidence"],
        "additionalProperties": False,
    }


def _validate(payload: object) -> DomainAnswer:
    if type(payload) is not dict or set(payload) != {"category", "evidence"}:
        raise c.ContractError("schema", "domain category")
    category, evidence = payload["category"], payload["evidence"]
    if category not in CATEGORIES or type(evidence) is not str:
        raise c.ContractError("schema", "domain category")
    return DomainAnswer(category, evidence)


def _normalize(text: str) -> str:
    return " ".join(text.split())


def _source(posting: c.DomainPostingInput) -> str:
    parts = [posting.position, posting.intro, *posting.main_tasks]
    parts += [*posting.requirements, *posting.preferred_points]
    return _normalize(" ".join(part for part in parts if part))


async def classify_domain(
    posting: c.DomainPostingInput,
    *,
    prompt: c.PromptSpec,
    limits: c.CallLimits,
    model_call: c.ModelCall[DomainAnswer],
) -> DomainDecision:
    """공고 1건의 category를 고른다. 판정 실패·근거 불일치는 모두 `etc`다(0022 결정 4·5)."""
    try:
        if type(prompt) is not c.PromptSpec or prompt.task_name != "domain_category":
            raise c.ContractError("schema", "domain_category prompt")
        if type(limits) is not c.CallLimits:
            raise c.ContractError("schema", "domain_category limits")
        if type(posting) is not c.DomainPostingInput:
            raise c.ContractError("schema", "domain posting")
    except c.ContractError as exc:
        # 모델을 부르기 전에 거절해 잘못된 입력으로 호출 비용을 쓰지 않는다.
        failure = c.CallFailure(exc.stage, "domain_category_input_invalid", "input rejected.")
        return DomainDecision("etc", None, failure, ())

    source = _source(posting)
    if not source:
        # 읽을 원문이 없으면 근거도 없으므로 호출하지 않는다.
        return DomainDecision("etc", None, None, ())

    request = c.ModelRequest(
        prompt=prompt,
        payload=asdict(posting),
        schema_name="DomainCategory",
        schema_version="1",
        output_schema=_output_schema(),
        limits=limits,
    )
    result = await model_call(request, _validate)
    if result.data is None:
        return DomainDecision("etc", None, result.failure, result.attempts)

    answer = result.data
    evidence = _normalize(answer.evidence)
    # 원문에 없는 근거로 category를 단정한 응답은 신뢰하지 않는다. 재호출하지 않는다.
    if answer.category == "etc" or not evidence or evidence not in source:
        return DomainDecision("etc", None, None, result.attempts)
    return DomainDecision(answer.category, evidence, None, result.attempts)
