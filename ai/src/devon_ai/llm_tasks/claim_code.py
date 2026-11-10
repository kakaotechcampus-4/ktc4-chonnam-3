"""선택 문서의 미검증 주장과 제공된 코드 원문만 한 배치로 대조한다."""

from dataclasses import asdict, dataclass
from re import fullmatch
from typing import Literal, cast

from devon_ai import contracts as c
from devon_ai.prompt_versions import require_prompt_version

SUPPORTED_PROMPT_VERSIONS = frozenset({"claim_code_v1"})
ComparisonStatus = Literal["consistent", "conflicting", "unverified"]
MAX_CLAIMS = 40
MAX_EVIDENCES = 16


@dataclass(frozen=True)
class ClaimForComparison:
    claim_id: str
    claim_type: str
    claim_text: str
    source_text: str
    source_version: str
    source_location: str


@dataclass(frozen=True)
class EvidenceQuote:
    evidence_id: str
    quote: str


@dataclass(frozen=True)
class ClaimComparison:
    claim_id: str
    status: ComparisonStatus
    reason: str
    evidence_quotes: tuple[EvidenceQuote, ...]
    limitations: tuple[str, ...]


@dataclass(frozen=True)
class ClaimComparisonResult:
    data: tuple[ClaimComparison, ...] | None
    failure: c.CallFailure | None
    attempts: tuple[c.AttemptMetadata, ...]

    @property
    def succeeded(self) -> bool:
        return self.failure is None


def unverified(claim: ClaimForComparison, reason: str) -> ClaimComparison:
    return ClaimComparison(
        claim.claim_id,
        "unverified",
        reason,
        (),
        (reason, "not_personal_contribution_evidence"),
    )


def unverified_reason(claim: ClaimForComparison, *, has_code: bool) -> str | None:
    if claim.claim_type in {"role", "outcome"}:
        return "personal_role_or_outcome_not_verifiable_from_code"
    if claim.claim_type not in {"implementation", "tech_usage"}:
        return "claim_type_not_supported"
    return None if has_code else "code_evidence_unavailable"


def _text(raw: object, field: str) -> str:
    if type(raw) is not str or not raw.strip():
        raise c.ContractError("schema", field)
    return raw


def _schema() -> dict[str, object]:
    quote = {
        "type": "object",
        "properties": {"evidence_id": {"type": "string"}, "quote": {"type": "string"}},
        "required": ["evidence_id", "quote"],
        "additionalProperties": False,
    }
    item = {
        "type": "object",
        "properties": {
            "claim_id": {"type": "string"},
            "status": {"type": "string", "enum": ["consistent", "conflicting", "unverified"]},
            "reason": {"type": "string"},
            "evidence_quotes": {"type": "array", "items": quote},
            "limitations": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["claim_id", "status", "reason", "evidence_quotes", "limitations"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {"comparisons": {"type": "array", "items": item}},
        "required": ["comparisons"],
        "additionalProperties": False,
    }


def _validate(
    raw: object,
    claims: tuple[ClaimForComparison, ...],
    evidences: tuple[c.Evidence, ...],
) -> tuple[ClaimComparison, ...]:
    if type(raw) is not dict or set(raw) != {"comparisons"} or type(raw["comparisons"]) is not list:
        raise c.ContractError("schema", "claim comparisons")
    expected = {item.claim_id for item in claims}
    sources = {item.evidence_id: item.content for item in evidences}
    results: dict[str, ClaimComparison] = {}
    for item in raw["comparisons"]:
        if type(item) is not dict or set(item) != {
            "claim_id",
            "status",
            "reason",
            "evidence_quotes",
            "limitations",
        }:
            raise c.ContractError("schema", "claim comparison")
        claim_id = _text(item["claim_id"], "claim id")
        status = item["status"]
        if type(status) is not str or status not in {"consistent", "conflicting", "unverified"}:
            raise c.ContractError("schema", "comparison status")
        reason = _text(item["reason"], "comparison reason")
        if type(item["evidence_quotes"]) is not list or type(item["limitations"]) is not list:
            raise c.ContractError("schema", "comparison references")
        limits = tuple(_text(value, "comparison limitation") for value in item["limitations"])
        quotes = []
        for quote in item["evidence_quotes"]:
            if type(quote) is not dict or set(quote) != {"evidence_id", "quote"}:
                raise c.ContractError("schema", "evidence quote")
            evidence_id = _text(quote["evidence_id"], "evidence id")
            text = _text(quote["quote"], "evidence quote")
            if evidence_id not in sources or text not in sources[evidence_id]:
                raise c.ContractError("semantic", "comparison evidence quote")
            quotes.append(EvidenceQuote(evidence_id, text))
        if claim_id not in expected or claim_id in results:
            raise c.ContractError("semantic", "comparison claim ids")
        if (status != "unverified" and not quotes) or (status == "unverified" and not limits):
            raise c.ContractError("semantic", "comparison basis")
        results[claim_id] = ClaimComparison(
            claim_id,
            cast(ComparisonStatus, status),
            reason,
            tuple(quotes),
            tuple(dict.fromkeys((*limits, "not_personal_contribution_evidence"))),
        )
    if set(results) != expected:
        raise c.ContractError("semantic", "comparison claim ids")
    return tuple(results[item.claim_id] for item in claims)


async def compare_claims(
    claims: tuple[ClaimForComparison, ...],
    evidences: tuple[c.Evidence, ...],
    *,
    prompt: c.PromptSpec,
    limits: c.CallLimits,
    model_call: c.ModelCall[tuple[ClaimComparison, ...]],
) -> ClaimComparisonResult:
    try:
        if (
            type(prompt) is not c.PromptSpec
            or type(limits) is not c.CallLimits
            or type(claims) is not tuple
            or any(type(item) is not ClaimForComparison for item in claims)
            or type(evidences) is not tuple
            or any(type(item) is not c.Evidence for item in evidences)
        ):
            raise c.ContractError("schema", "claim comparison input")
        require_prompt_version(
            prompt, task_name="claim_code", supported_versions=SUPPORTED_PROMPT_VERSIONS
        )
        if len(claims) > MAX_CLAIMS or len(evidences) > MAX_EVIDENCES:
            raise c.ContractError("schema", "comparison input budget")
        ids = []
        for item in claims:
            for value in asdict(item).values():
                _text(value, "claim comparison input")
            if fullmatch(r"[0-9a-f]{64}", item.source_version) is None:
                raise c.ContractError("schema", "claim source version")
            ids.append(item.claim_id)
        if len(set(ids)) != len(ids):
            raise c.ContractError("semantic", "claim ids")
        if len({item.evidence_id for item in evidences}) != len(evidences):
            raise c.ContractError("semantic", "comparison evidence ids")
        for source in evidences:
            if (
                source.evidence_id is None
                or source.path is None
                or source.git_ref is None
                or source.source_kind != "file"
            ):
                raise c.ContractError("semantic", "comparison code source")
    except c.ContractError as error:
        return ClaimComparisonResult(
            None,
            c.CallFailure(error.stage, "claim_comparison_input_invalid", "Input rejected."),
            (),
        )
    # 역할·성과는 코드의 존재로 검증할 수 없다. 모델 판단으로 승격하지 않는다.
    unresolved = {
        item.claim_id: unverified(item, reason)
        for item in claims
        if (reason := unverified_reason(item, has_code=bool(evidences))) is not None
    }
    technical = tuple(item for item in claims if item.claim_id not in unresolved)
    if not technical or not evidences:
        return ClaimComparisonResult(tuple(unresolved[item.claim_id] for item in claims), None, ())
    request = c.ModelRequest(
        prompt=prompt,
        payload={
            "claims": [asdict(item) for item in technical],
            "evidences": [asdict(item) for item in evidences],
        },
        schema_name="DocumentClaimComparison",
        schema_version="1",
        output_schema=_schema(),
        limits=limits,
    )
    result = await model_call(request, lambda raw: _validate(raw, technical, evidences))
    if result.data is None:
        return ClaimComparisonResult(None, result.failure, result.attempts)
    unresolved.update({item.claim_id: item for item in result.data})
    return ClaimComparisonResult(
        tuple(unresolved[item.claim_id] for item in claims), None, result.attempts
    )
