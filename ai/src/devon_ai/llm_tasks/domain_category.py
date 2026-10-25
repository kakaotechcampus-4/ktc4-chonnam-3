"""공고 도메인 category 판정. 결정은 spec/ai/decisions/0022·0028을 따른다.

prompt 로드·provider I/O·`postings.domain_category` 저장은 BE 책임이다. 이 모듈은 요청 생성과
응답 검증, 근거 문단 ID의 원문 복원만 맡는다.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, get_args

from devon_ai import contracts as c

DomainCategory = Literal["finance", "game", "travel", "shopping", "medical", "mobility", "etc"]
CATEGORIES: tuple[DomainCategory, ...] = get_args(DomainCategory)
FIELDS = ("position", "intro", "main_tasks", "requirements", "preferred_points")
SCHEMA_VERSION = "2"
_BLANK_LINE = re.compile(r"\r?\n(?:[^\S\r\n]*\r?\n)+")


@dataclass(frozen=True)
class DomainAnswer:
    category: DomainCategory
    # 선택한 문단 ID로 복원한 원문. `etc`이면 None.
    evidence: str | None


@dataclass(frozen=True)
class DomainDecision:
    """저장할 category와 기록용 호출 정보. 호출이 실패해도 category는 항상 7종 중 하나다."""

    category: DomainCategory
    # 모델이 고른 문단의 원문. `etc`이거나 판정에 실패하면 None.
    evidence: str | None
    failure: c.CallFailure | None
    attempts: tuple[c.AttemptMetadata, ...]


def _output_schema() -> dict[str, object]:
    return {
        "type": "object",
        "properties": {
            "category": {"type": "string", "enum": list(CATEGORIES)},
            "evidence_id": {"type": ["string", "null"]},
        },
        "required": ["category", "evidence_id"],
        "additionalProperties": False,
    }


def _paragraphs(posting: c.DomainPostingInput) -> dict[str, list[dict[str, str]]]:
    """필드별 원문을 `[{id, text}]` 문단 목록으로 바꾼다. 문단 안의 줄바꿈·문자는 고치지 않는다."""
    result: dict[str, list[dict[str, str]]] = {}
    for name in FIELDS:
        value = getattr(posting, name)
        items = (value,) if isinstance(value, str) else (value or ())
        texts = [part for item in items for part in _BLANK_LINE.split(item)]
        # 빈 문단만 제외한다. 선택한 원문의 양 끝 공백도 재작성하지 않는다.
        texts = [text for text in texts if text.strip()]
        result[name] = [{"id": f"{name}:{i}", "text": text} for i, text in enumerate(texts)]
    return result


def _validator(source: dict[str, str]) -> Callable[[object], DomainAnswer]:
    """이번 요청의 문단 표로만 ID를 확인한다. 근거 오류는 semantic이라 재시도하지 않는다."""

    def validate(payload: object) -> DomainAnswer:
        if type(payload) is not dict or set(payload) != {"category", "evidence_id"}:
            raise c.ContractError("schema", "domain category")
        category, evidence_id = payload["category"], payload["evidence_id"]
        if category not in CATEGORIES or (evidence_id is not None and type(evidence_id) is not str):
            raise c.ContractError("schema", "domain category")
        if category == "etc":
            if evidence_id is not None:
                raise c.ContractError("semantic", "evidence_id")
            return DomainAnswer("etc", None)
        if evidence_id not in source:
            raise c.ContractError("semantic", "evidence_id")
        return DomainAnswer(category, source[evidence_id])

    return validate


async def classify_domain(
    posting: c.DomainPostingInput,
    *,
    prompt: c.PromptSpec,
    limits: c.CallLimits,
    model_call: c.ModelCall[DomainAnswer],
) -> DomainDecision:
    """공고 1건의 category를 고른다. 호출·근거 검증 실패는 기록을 남기고 `etc`다(0022 결정 4·5)."""
    try:
        if (
            type(prompt) is not c.PromptSpec
            or prompt.task_name != "domain_category"
            or prompt.version != "domain_category_v2"
        ):
            raise c.ContractError("schema", "domain_category prompt")
        if type(limits) is not c.CallLimits:
            raise c.ContractError("schema", "domain_category limits")
        if type(posting) is not c.DomainPostingInput:
            raise c.ContractError("schema", "domain posting")
    except c.ContractError as exc:
        # 모델을 부르기 전에 거절해 잘못된 입력으로 호출 비용을 쓰지 않는다.
        failure = c.CallFailure(exc.stage, "domain_category_input_invalid", "input rejected.")
        return DomainDecision("etc", None, failure, ())

    paragraphs = _paragraphs(posting)
    source = {p["id"]: p["text"] for items in paragraphs.values() for p in items}
    if not source:
        # 읽을 원문이 없으면 근거도 없으므로 호출하지 않는다.
        return DomainDecision("etc", None, None, ())

    request = c.ModelRequest(
        prompt=prompt,
        payload=dict(paragraphs),
        schema_name="DomainCategory",
        schema_version=SCHEMA_VERSION,
        output_schema=_output_schema(),
        limits=limits,
    )
    result = await model_call(request, _validator(source))
    if result.data is None:
        return DomainDecision("etc", None, result.failure, result.attempts)
    return DomainDecision(result.data.category, result.data.evidence, None, result.attempts)
