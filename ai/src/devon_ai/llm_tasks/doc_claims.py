"""포트폴리오 문서 Claim 추출. 결정은 spec/ai/decisions/0029-document-claims.md를 따른다.

prompt 로드·provider I/O·`document_claims` 저장은 BE 책임이다. 이 모듈은 요청 생성과 응답 검증,
근거 줄 ID의 줄 번호 복원만 맡는다. Claim은 문서에 적힌 주장일 뿐 확인된 사실이 아니다.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, get_args

from devon_ai import contracts as c

ClaimType = Literal["tech_usage", "implementation", "outcome", "role"]
CLAIM_TYPES: tuple[ClaimType, ...] = get_args(ClaimType)
SCHEMA_VERSION = "1"
MAX_CLAIMS = 20
MAX_TECH_TAGS = 5
_ITEM_KEYS = {"claim_text", "claim_type", "tech_tags", "line_id"}


@dataclass(frozen=True)
class DocumentClaim:
    claim_text: str
    claim_type: ClaimType
    tech_tags: tuple[str, ...]
    # 추출 텍스트에서 비어 있지 않은 줄의 순번(0부터). `document_claims.paragraph_no`에 저장한다.
    paragraph_no: int
    # 선택한 줄의 원문. 검증·기록용이며 DB 컬럼이 없어 저장하지 않는다.
    source_line: str


@dataclass(frozen=True)
class ClaimExtraction:
    """추출 결과와 기록용 호출 정보. 실패해도 분석을 막지 않도록 claims는 빈 tuple이다."""

    claims: tuple[DocumentClaim, ...]
    failure: c.CallFailure | None
    attempts: tuple[c.AttemptMetadata, ...]


def _output_schema() -> dict[str, object]:
    item = {
        "type": "object",
        "properties": {
            "claim_text": {"type": "string"},
            "claim_type": {"type": "string", "enum": list(CLAIM_TYPES)},
            "tech_tags": {"type": "array", "items": {"type": "string"}},
            "line_id": {"type": "string"},
        },
        "required": sorted(_ITEM_KEYS),
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {"claims": {"type": "array", "items": item}},
        "required": ["claims"],
        "additionalProperties": False,
    }


def _lines(text: str) -> list[dict[str, str]]:
    """비어 있지 않은 줄마다 `L<순번>` ID를 붙인다. PDF·DOCX 추출은 문단을 빈 줄로 나누지 않는다."""
    # 빈 줄만 제외한다. `source_line`이 원문과 같도록 양 끝 공백도 고치지 않는다.
    lines = [line for line in text.splitlines() if line.strip()]
    return [{"id": f"L{i}", "text": line} for i, line in enumerate(lines)]


def _text(value: object) -> bool:
    return type(value) is str and bool(value.strip())


def _validator(source: dict[str, str]) -> Callable[[object], tuple[DocumentClaim, ...]]:
    """이번 요청의 줄 표로만 ID를 확인한다. 없는 줄 ID는 semantic이라 재시도하지 않는다."""

    def validate(payload: object) -> tuple[DocumentClaim, ...]:
        if type(payload) is not dict or set(payload) != {"claims"}:
            raise c.ContractError("schema", "document claims")
        items = payload["claims"]
        if type(items) is not list or len(items) > MAX_CLAIMS:
            raise c.ContractError("schema", "claims")
        claims = []
        for item in items:
            if type(item) is not dict or set(item) != _ITEM_KEYS:
                raise c.ContractError("schema", "claim")
            tags = item["tech_tags"]
            if (
                not _text(item["claim_text"])
                or item["claim_type"] not in CLAIM_TYPES
                or type(tags) is not list
                or len(tags) > MAX_TECH_TAGS
                or not all(_text(tag) for tag in tags)
                or type(item["line_id"]) is not str
            ):
                raise c.ContractError("schema", "claim")
            if item["line_id"] not in source:
                raise c.ContractError("semantic", "line_id")
            claims.append(
                DocumentClaim(
                    item["claim_text"].strip(),
                    item["claim_type"],
                    tuple(dict.fromkeys(tag.strip() for tag in tags)),
                    int(item["line_id"][1:]),
                    source[item["line_id"]],
                )
            )
        return tuple(claims)

    return validate


async def extract_claims(
    text: str,
    *,
    prompt: c.PromptSpec,
    limits: c.CallLimits,
    model_call: c.ModelCall[tuple[DocumentClaim, ...]],
) -> ClaimExtraction:
    """포트폴리오 추출 텍스트 1건에서 Claim을 뽑는다. 호출·검증 실패는 기록하고 빈 결과다."""
    try:
        if (
            type(prompt) is not c.PromptSpec
            or prompt.task_name != "doc_claims"
            or prompt.version != "doc_claims_v1"
        ):
            raise c.ContractError("schema", "doc_claims prompt")
        if type(limits) is not c.CallLimits:
            raise c.ContractError("schema", "doc_claims limits")
        if type(text) is not str:
            raise c.ContractError("schema", "document text")
    except c.ContractError as exc:
        # 모델을 부르기 전에 거절해 잘못된 입력으로 호출 비용을 쓰지 않는다.
        failure = c.CallFailure(exc.stage, "doc_claims_input_invalid", "input rejected.")
        return ClaimExtraction((), failure, ())

    lines = _lines(text)
    if not lines:
        # 읽을 원문이 없으면 주장도 없으므로 호출하지 않는다.
        return ClaimExtraction((), None, ())

    request = c.ModelRequest(
        prompt=prompt,
        payload={"lines": lines},
        schema_name="DocumentClaims",
        schema_version=SCHEMA_VERSION,
        output_schema=_output_schema(),
        limits=limits,
    )
    result = await model_call(request, _validator({line["id"]: line["text"] for line in lines}))
    if result.data is None:
        return ClaimExtraction((), result.failure, result.attempts)
    return ClaimExtraction(result.data, None, result.attempts)
