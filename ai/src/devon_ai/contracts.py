"""Internal candidates and pure checks; never DB rows or public wire payloads.

See spec/ai/designs/2026-09-21-question-eval-contracts.md for the adopted subset.
Structural decoding alone does not establish semantic validity or BE acceptance.
"""

from dataclasses import dataclass, fields, is_dataclass
from types import UnionType
from typing import Literal, Union, cast, get_args, get_origin, get_type_hints

PersonaId = Literal["tech_lead", "hr_manager", "domain_lead"]
FailureStage = Literal["parse", "schema", "semantic"]


class ContractError(ValueError):
    """A local failure with a safe field label, never the rejected raw value."""

    def __init__(self, stage: FailureStage, field: str) -> None:
        self.stage = stage
        super().__init__(f"{stage}: {field}")


class _Contract:
    def __post_init__(self) -> None:
        for name, annotation in get_type_hints(type(self)).items():
            _convert(annotation, getattr(self, name), name, wire=False)


def _convert(annotation: object, value: object, field: str, *, wire: bool) -> object:
    origin, args = get_origin(annotation), get_args(annotation)
    if origin is Literal:
        if any(type(value) is type(option) and value == option for option in args):
            return value
    elif origin is UnionType or origin is Union:
        for option in args:
            try:
                return _convert(option, value, field, wire=wire)
            except ContractError:
                pass
    elif annotation is type(None) and value is None:
        return None
    elif annotation is str:
        if type(value) is str and value.strip():
            return value
    elif annotation is bool and type(value) is bool:
        return value
    elif origin is tuple and len(args) == 2 and args[1] is Ellipsis:
        if type(value) is (list if wire else tuple):
            return tuple(_convert(args[0], item, field, wire=wire) for item in value)
    elif isinstance(annotation, type) and issubclass(annotation, _Contract):
        if not wire and type(value) is annotation:
            return value
        if wire and isinstance(value, dict) and is_dataclass(annotation):
            if set(value) == {item.name for item in fields(annotation)}:
                hints = get_type_hints(annotation)
                return annotation(
                    **{
                        name: _convert(kind, value[name], name, wire=True)
                        for name, kind in hints.items()
                    }
                )
    raise ContractError("schema", field)


def decode[T: _Contract](contract_type: type[T], payload: object) -> T:
    """Decode an already parsed object strictly; return an untrusted candidate."""
    return cast(T, _convert(contract_type, payload, contract_type.__name__, wire=True))


def _unique(values: tuple[str, ...], field: str) -> None:
    if len(set(values)) != len(values):
        raise ContractError("semantic", field)


@dataclass(frozen=True)
class Persona(_Contract):
    persona: PersonaId
    question_responsibilities: tuple[str, ...]
    avoided_assumptions: tuple[str, ...]

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.question_responsibilities or not self.avoided_assumptions:
            raise ContractError("schema", "persona configuration")


def validate_personas(personas: tuple[Persona, ...]) -> tuple[Persona, ...]:
    """Require the full FIX set; BE owns wording and its policy review."""
    _convert(tuple[Persona, ...], personas, "personas", wire=False)
    names = tuple(item.persona for item in personas)
    _unique(names, "personas")
    if set(names) != {"tech_lead", "hr_manager", "domain_lead"}:
        raise ContractError("semantic", "personas")
    return personas


@dataclass(frozen=True)
class RequiredPoint(_Contract):
    key: str
    description: str


@dataclass(frozen=True)
class QuestionContract(_Contract):
    purpose: str
    required_points: tuple[RequiredPoint, ...]
    assumptions: tuple[str, ...]
    basis_refs: tuple[str, ...]
    evaluation_scope: str

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.required_points:
            raise ContractError("schema", "required_points")
        _unique(tuple(point.key for point in self.required_points), "required_points")
        _unique(self.basis_refs, "basis_refs")


@dataclass(frozen=True)
class Question(_Contract):
    persona: PersonaId
    text: str
    topic_code: str
    question_contract: QuestionContract
    evidence_refs: tuple[str, ...]
    jd_requirement_ids: tuple[str, ...]


@dataclass(frozen=True)
class QuestionReview:
    """Trusted caller's semantic review bound to exact wording, not model output.

    The caller must independently check the actual requirements, premises and
    evaluation scope. This module does not perform natural-language judgement.
    """

    text: str
    question_contract: QuestionContract

    def __post_init__(self) -> None:
        _convert(str, self.text, "review text", wire=False)
        _convert(QuestionContract, self.question_contract, "review contract", wire=False)


@dataclass(frozen=True, init=False)
class ContractChecked[T]:
    """Pure contract checks passed; NOT persisted, authorized or ready to publish."""

    data: T

    def __init__(self) -> None:
        raise TypeError("Use a contract validation function")


def _checked[T](candidate: T) -> ContractChecked[T]:
    result: ContractChecked[T] = object.__new__(ContractChecked)
    object.__setattr__(result, "data", candidate)
    return result


def _references(values: tuple[str, ...], registered: frozenset[str], field: str) -> None:
    if type(registered) is not frozenset or any(
        type(ref) is not str or not ref.strip() for ref in registered
    ):
        raise ContractError("schema", "reference registry")
    _unique(values, field)
    if not set(values).issubset(registered):
        raise ContractError("semantic", field)


def validate_question(
    candidate: Question,
    *,
    review: QuestionReview,
    allowed_personas: tuple[PersonaId, ...],
    evidence_refs: frozenset[str],
    basis_refs: frozenset[str],
    jd_requirement_ids: frozenset[str],
) -> ContractChecked[Question]:
    """Check the candidate against caller-reviewed wording, scope and BE refs."""
    _convert(Question, candidate, "question", wire=False)
    _convert(tuple[PersonaId, ...], allowed_personas, "allowed_personas", wire=False)
    if type(review) is not QuestionReview:
        raise ContractError("schema", "question review")
    if candidate.persona not in allowed_personas:
        raise ContractError("semantic", "persona")
    _references(candidate.evidence_refs, evidence_refs, "evidence_refs")
    _references(candidate.jd_requirement_ids, jd_requirement_ids, "jd_requirement_ids")
    _references(candidate.question_contract.basis_refs, basis_refs, "basis_refs")
    if candidate.text != review.text or candidate.question_contract != review.question_contract:
        raise ContractError("semantic", "question requirements")
    return _checked(candidate)


@dataclass(frozen=True)
class CoveredPoint(_Contract):
    key: str
    answer_quotes: tuple[str, ...]


@dataclass(frozen=True)
class TechnicalAssessment(_Contract):
    explanation: str
    answer_quotes: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    limitations: tuple[str, ...]


@dataclass(frozen=True)
class ClaimCheck(_Contract):
    claim_text: str
    status: Literal["supported", "partially_supported", "unverified", "conflicting"]
    evidence_refs: tuple[str, ...]
    limitations: tuple[str, ...]


@dataclass(frozen=True)
class VerificationRequest(_Contract):
    claim_text: str
    purpose: str
    repository_id: str
    git_ref: str
    allowed_paths: tuple[str, ...]


@dataclass(frozen=True)
class AnswerAnalysis(_Contract):
    evaluation_status: Literal["evaluated", "needs_clarification", "not_evaluable"]
    sufficiency: Literal["sufficient", "partial", "insufficient"] | None
    covered_points: tuple[CoveredPoint, ...]
    missing_points: tuple[str, ...]
    technical_assessment: TechnicalAssessment
    contribution_scope: Literal["self", "shared", "teammate", "unknown"]
    contribution_quotes: tuple[str, ...]
    claim_checks: tuple[ClaimCheck, ...]
    needs_verification: bool
    verification_requests: tuple[VerificationRequest, ...]
    limitations: tuple[str, ...]


def _checked_data[T](value: ContractChecked[T], expected: type[T]) -> T:
    if type(value) is not ContractChecked or type(value.data) is not expected:
        raise ContractError("schema", "contract checked input")
    return value.data


def _quotes(quotes: tuple[str, ...], text: str) -> None:
    if any(quote not in text for quote in quotes):
        raise ContractError("semantic", "answer quotes")


def _requests(
    requests: tuple[VerificationRequest, ...],
    allowed_locations: frozenset[tuple[str, str, str]],
) -> None:
    if len(set(requests)) != len(requests):
        raise ContractError("semantic", "duplicate requests")
    for request in requests:
        _unique(request.allowed_paths, "allowed_paths")
        if not request.allowed_paths or any(
            (request.repository_id, request.git_ref, path) not in allowed_locations
            for path in request.allowed_paths
        ):
            raise ContractError("semantic", "verification scope")


def validate_analysis(
    candidate: AnswerAnalysis,
    *,
    question: ContractChecked[Question],
    answer_text: str,
    evidence_refs: frozenset[str],
    allowed_locations: frozenset[tuple[str, str, str]],
) -> ContractChecked[AnswerAnalysis]:
    """Validate links and consistency, without generating or changing assessments."""
    _convert(AnswerAnalysis, candidate, "analysis", wire=False)
    _convert(str, answer_text, "submitted answer", wire=False)
    contract = _checked_data(question, Question).question_contract
    keys = frozenset(point.key for point in contract.required_points)
    covered = tuple(point.key for point in candidate.covered_points)
    _references(covered, keys, "covered_points")
    _references(candidate.missing_points, keys, "missing_points")
    if candidate.sufficiency is None:
        if not candidate.limitations or covered or candidate.missing_points:
            raise ContractError("semantic", "unevaluable sufficiency")
    elif set(covered) | set(candidate.missing_points) != keys:
        raise ContractError("semantic", "point coverage")
    if candidate.evaluation_status != "evaluated" and not candidate.limitations:
        raise ContractError("semantic", "evaluation limitations")
    if candidate.evaluation_status == "not_evaluable" and candidate.sufficiency is not None:
        raise ContractError("semantic", "evaluation_status")
    if candidate.sufficiency == "sufficient" and candidate.missing_points:
        raise ContractError("semantic", "sufficiency")
    if set(covered).intersection(candidate.missing_points) and not candidate.limitations:
        raise ContractError("semantic", "partially covered point limitations")
    for point in candidate.covered_points:
        if not point.answer_quotes:
            raise ContractError("semantic", "covered point quotes")
        _quotes(point.answer_quotes, answer_text)
    technical = candidate.technical_assessment
    _quotes(technical.answer_quotes, answer_text)
    _references(technical.evidence_refs, evidence_refs, "technical evidence")
    _quotes(candidate.contribution_quotes, answer_text)
    if candidate.contribution_scope != "unknown" and not candidate.contribution_quotes:
        raise ContractError("semantic", "contribution quotes")
    for claim in candidate.claim_checks:
        _quotes((claim.claim_text,), answer_text)
        _references(claim.evidence_refs, evidence_refs, "claim evidence")
        if claim.status != "unverified" and not claim.evidence_refs:
            raise ContractError("semantic", "claim evidence required")
        if claim.status == "unverified" and not claim.limitations:
            raise ContractError("semantic", "claim limitations")
    if candidate.needs_verification != bool(candidate.verification_requests):
        raise ContractError("semantic", "needs_verification")
    _requests(candidate.verification_requests, allowed_locations)
    for request in candidate.verification_requests:
        _quotes((request.claim_text,), answer_text)
    return _checked(candidate)


@dataclass(frozen=True)
class DirectorDecision(_Contract):
    next_step: Literal["ask", "retrieve", "finish"]
    intent: str
    persona: PersonaId | None
    target: str | None
    tool_requests: tuple[VerificationRequest, ...]
    reason_summary: str


@dataclass(frozen=True)
class CandidateFailure(_Contract):
    stage: FailureStage
    reason_summary: str


@dataclass(frozen=True)
class CandidateRecovery(_Contract):
    recovery: Literal["rewrite", "replan", "no_valid_candidate"]
    reason_summary: str


def validate_decision(
    candidate: DirectorDecision,
    *,
    question: ContractChecked[Question] | None,
    allowed_personas: tuple[PersonaId, ...],
    finish_allowed: bool,
    allowed_locations: frozenset[tuple[str, str, str]],
) -> ContractChecked[DirectorDecision]:
    """Validate combinations against caller permissions; do not advance any turn."""
    _convert(DirectorDecision, candidate, "decision", wire=False)
    _convert(tuple[PersonaId, ...], allowed_personas, "allowed_personas", wire=False)
    _convert(bool, finish_allowed, "finish_allowed", wire=False)
    if candidate.next_step == "ask":
        if question is None:
            raise ContractError("semantic", "ask question required")
        value = _checked_data(question, Question)
        if (
            candidate.persona not in allowed_personas
            or candidate.persona != value.persona
            or candidate.target != value.question_contract.purpose
            or candidate.tool_requests
        ):
            raise ContractError("semantic", "ask consistency")
    else:
        if question is not None or candidate.persona is not None:
            raise ContractError("semantic", "non-question decision")
        if candidate.next_step == "retrieve":
            if not candidate.tool_requests or candidate.target is None:
                raise ContractError("semantic", "retrieve requests required")
            _requests(candidate.tool_requests, allowed_locations)
        elif not finish_allowed or candidate.tool_requests or candidate.target is not None:
            raise ContractError("semantic", "finish permission")
    return _checked(candidate)
