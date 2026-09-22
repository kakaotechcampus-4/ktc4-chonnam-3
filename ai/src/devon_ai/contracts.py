"""AI 내부 후보·검증 계약과 공급자에 종속되지 않는 모델 호출 계약."""

from collections.abc import Awaitable, Callable
from dataclasses import MISSING, dataclass, field, fields, is_dataclass
from math import isfinite
from re import fullmatch
from types import UnionType
from typing import Literal, Union, cast, get_args, get_origin, get_type_hints

FailureStage = Literal["parse", "schema", "semantic"]
CallFailureStage = Literal["timeout", "provider", "parse", "schema", "semantic", "budget"]


class ContractError(ValueError):
    """거절한 원문이나 비밀값 대신 실패 단계와 필드만 담는 검증 오류."""

    def __init__(self, stage: FailureStage, field: str) -> None:
        self.stage = stage
        self.field = field
        super().__init__(f"{stage}: {field}")


def _text(value: object, name: str) -> None:
    if type(value) is not str or not value.strip():
        raise ContractError("schema", name)


def _positive_int(value: object, name: str, *, allow_zero: bool = False) -> None:
    minimum = 0 if allow_zero else 1
    if type(value) is not int or value < minimum:
        raise ContractError("schema", name)


@dataclass(frozen=True)
class PromptSpec:
    task_name: str
    version: str
    model: str
    template: str = field(repr=False)

    def __post_init__(self) -> None:
        for name in ("task_name", "version", "model", "template"):
            _text(getattr(self, name), name)


@dataclass(frozen=True)
class CallLimits:
    timeout_seconds: float
    max_output_tokens: int
    max_input_bytes: int
    max_response_bytes: int

    def __post_init__(self) -> None:
        timeout = self.timeout_seconds
        if type(timeout) not in (int, float) or not isfinite(timeout) or timeout <= 0:
            raise ContractError("schema", "timeout_seconds")
        for name in ("max_output_tokens", "max_input_bytes", "max_response_bytes"):
            _positive_int(getattr(self, name), name)


@dataclass(frozen=True)
class ModelRequest:
    prompt: PromptSpec
    payload: dict[str, object] = field(repr=False)
    schema_name: str
    schema_version: str
    output_schema: dict[str, object]
    limits: CallLimits
    # 요청별 상한은 공통 호출 계층의 총 2회 상한을 줄일 수만 있고 늘릴 수는 없다.
    max_attempts: int = 2

    def __post_init__(self) -> None:
        if type(self.prompt) is not PromptSpec:
            raise ContractError("schema", "prompt")
        if type(self.payload) is not dict or any(type(key) is not str for key in self.payload):
            raise ContractError("schema", "payload")
        if type(self.output_schema) is not dict or any(
            type(key) is not str for key in self.output_schema
        ):
            raise ContractError("schema", "output_schema")
        _text(self.schema_name, "schema_name")
        _text(self.schema_version, "schema_version")
        if type(self.limits) is not CallLimits:
            raise ContractError("schema", "limits")
        if type(self.max_attempts) is not int or self.max_attempts not in (1, 2):
            raise ContractError("schema", "max_attempts")


@dataclass(frozen=True)
class CallFailure:
    stage: CallFailureStage
    error_code: str
    reason_summary: str

    def __post_init__(self) -> None:
        if self.stage not in ("timeout", "provider", "parse", "schema", "semantic", "budget"):
            raise ContractError("schema", "stage")
        _text(self.error_code, "error_code")
        _text(self.reason_summary, "reason_summary")


@dataclass(frozen=True)
class AttemptMetadata:
    attempt: int
    provider: str
    model: str
    prompt_version: str
    schema_version: str
    latency_ms: int
    input_tokens: int | None
    output_tokens: int | None
    error_stage: str | None = None
    error_code: str | None = None
    raw_output: str | None = field(default=None, repr=False)
    response_id: str | None = None

    def __post_init__(self) -> None:
        _positive_int(self.attempt, "attempt")
        _positive_int(self.latency_ms, "latency_ms", allow_zero=True)
        for name in ("provider", "model", "prompt_version", "schema_version"):
            _text(getattr(self, name), name)
        for name in ("input_tokens", "output_tokens"):
            value = getattr(self, name)
            if value is not None:
                _positive_int(value, name, allow_zero=True)
        if self.error_stage is not None and self.error_stage not in (
            "timeout",
            "provider",
            "parse",
            "schema",
            "semantic",
            "budget",
        ):
            raise ContractError("schema", "error_stage")
        for name in ("error_code", "response_id"):
            value = getattr(self, name)
            if value is not None:
                _text(value, name)
        if self.raw_output is not None and type(self.raw_output) is not str:
            raise ContractError("schema", "raw_output")


@dataclass(frozen=True)
class ModelResult[T]:
    data: T | None = field(repr=False)
    failure: CallFailure | None
    attempts: tuple[AttemptMetadata, ...]

    def __post_init__(self) -> None:
        if (self.data is None) == (self.failure is None):
            raise ContractError("schema", "model result outcome")
        if self.failure is not None and type(self.failure) is not CallFailure:
            raise ContractError("schema", "failure")
        if type(self.attempts) is not tuple or any(
            type(attempt) is not AttemptMetadata for attempt in self.attempts
        ):
            raise ContractError("schema", "attempts")
        if self.failure is None and not self.attempts:
            raise ContractError("schema", "attempts")

    @property
    def succeeded(self) -> bool:
        return self.failure is None


type ModelCall[T] = Callable[[ModelRequest, Callable[[object], T]], Awaitable[ModelResult[T]]]


class _Contract:
    def __post_init__(self) -> None:
        for name, annotation in get_type_hints(type(self)).items():
            _convert(annotation, getattr(self, name), name, wire=False)


def _convert(annotation: object, value: object, name: str, *, wire: bool) -> object:
    origin, args = get_origin(annotation), get_args(annotation)
    if origin is Literal:
        if any(type(value) is type(option) and value == option for option in args):
            return value
    elif origin is UnionType or origin is Union:
        for option in args:
            try:
                return _convert(option, value, name, wire=wire)
            except ContractError as error:
                if error.stage != "schema":
                    raise
    elif annotation is type(None) and value is None:
        return None
    elif annotation is str:
        _text(value, name)
        return value
    elif annotation is bool and type(value) is bool:
        return value
    elif annotation is int and type(value) is int:
        return value
    elif origin is tuple and len(args) == 2 and args[1] is Ellipsis:
        sequence_type = list if wire else tuple
        if type(value) is sequence_type:
            return tuple(_convert(args[0], item, name, wire=wire) for item in value)
    elif isinstance(annotation, type) and issubclass(annotation, _Contract):
        if not wire and type(value) is annotation:
            return value
        if wire and type(value) is dict and is_dataclass(annotation):
            hints = get_type_hints(annotation)
            converted: dict[str, object] = {}
            for item in fields(annotation):
                if item.name in value:
                    converted[item.name] = _convert(
                        hints[item.name], value[item.name], item.name, wire=True
                    )
                elif item.default is not MISSING:
                    converted[item.name] = item.default
                else:
                    raise ContractError("schema", item.name)
            return annotation(**converted)
    raise ContractError("schema", name)


def decode[T: _Contract](contract_type: type[T], payload: object) -> T:
    """파싱된 JSON을 불변 후보로 변환한다. 의미 검증을 통과한 성공 결과는 아니다."""
    return cast(T, _convert(contract_type, payload, contract_type.__name__, wire=True))


def _unique(values: tuple[object, ...], name: str) -> None:
    if len(set(values)) != len(values):
        raise ContractError("semantic", name)


PersonaId = Literal["tech_lead", "hr_manager", "domain_lead"]
BasisKind = Literal["evidence", "jd_requirement", "job_posting", "answer_turn"]


@dataclass(frozen=True)
class BasisRef(_Contract):
    kind: BasisKind
    id: str


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
    basis_refs: tuple[BasisRef, ...]
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
    text: str
    question_contract: QuestionContract

    def __post_init__(self) -> None:
        _text(self.text, "review text")
        if type(self.question_contract) is not QuestionContract:
            raise ContractError("schema", "review contract")


@dataclass(frozen=True, init=False)
class ContractChecked[T]:
    """검증 함수만 생성하며 저장·직렬화 경계에 검증 완료 여부를 전달한다."""

    data: T

    def __init__(self) -> None:
        raise TypeError("Use a contract validation function")


def _checked[T](candidate: T) -> ContractChecked[T]:
    result: ContractChecked[T] = object.__new__(ContractChecked)
    object.__setattr__(result, "data", candidate)
    return result


def _references[T](values: tuple[T, ...], registered: frozenset[T], name: str) -> None:
    if type(registered) is not frozenset:
        raise ContractError("schema", "reference registry")
    _unique(cast(tuple[object, ...], values), name)
    if not set(values).issubset(registered):
        raise ContractError("semantic", name)


def validate_question_candidate(
    candidate: Question,
    *,
    allowed_personas: tuple[PersonaId, ...],
    evidence_refs: frozenset[str],
    basis_refs: frozenset[BasisRef],
    jd_requirement_ids: frozenset[str],
) -> Question:
    """구조·허용 Persona·등록 참조만 검사한다. 질문의 의미 검토를 대신하지 않는다."""
    _convert(Question, candidate, "question", wire=False)
    _convert(tuple[PersonaId, ...], allowed_personas, "allowed_personas", wire=False)
    if candidate.persona not in allowed_personas:
        raise ContractError("semantic", "persona")
    _references(candidate.evidence_refs, evidence_refs, "evidence_refs")
    _references(candidate.question_contract.basis_refs, basis_refs, "basis_refs")
    _references(candidate.jd_requirement_ids, jd_requirement_ids, "jd_requirement_ids")
    return candidate


def validate_question(
    candidate: Question,
    *,
    review: QuestionReview,
    allowed_personas: tuple[PersonaId, ...],
    evidence_refs: frozenset[str],
    basis_refs: frozenset[BasisRef],
    jd_requirement_ids: frozenset[str],
) -> ContractChecked[Question]:
    """정책 검증과 정확한 문장·계약에 결합된 독립 검토를 모두 요구한다."""
    validate_question_candidate(
        candidate,
        allowed_personas=allowed_personas,
        evidence_refs=evidence_refs,
        basis_refs=basis_refs,
        jd_requirement_ids=jd_requirement_ids,
    )
    if type(review) is not QuestionReview:
        raise ContractError("schema", "question review")
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
class ContributionScope(_Contract):
    scope: Literal["self", "shared", "teammate", "unknown"]
    answer_quotes: tuple[str, ...]


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
    contribution_scope: ContributionScope
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


def _locations(value: object) -> frozenset[tuple[str, str, str]]:
    if type(value) is not frozenset or any(
        type(location) is not tuple
        or len(location) != 3
        or any(type(part) is not str or not part.strip() for part in location)
        for location in value
    ):
        raise ContractError("schema", "allowed_locations")
    return cast(frozenset[tuple[str, str, str]], value)


def _requests(
    requests: tuple[VerificationRequest, ...],
    allowed_locations: frozenset[tuple[str, str, str]],
) -> None:
    locations = _locations(allowed_locations)
    _unique(cast(tuple[object, ...], requests), "verification requests")
    for request in requests:
        _unique(cast(tuple[object, ...], request.allowed_paths), "allowed_paths")
        if not request.allowed_paths or any(
            (request.repository_id, request.git_ref, path) not in locations
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
    # 질문하지 않은 항목을 평가에 섞거나 답변 원문에 없는 인용을 근거로 만들지 못하게 한다.
    _convert(AnswerAnalysis, candidate, "analysis", wire=False)
    _text(answer_text, "submitted answer")
    contract = _checked_data(question, Question).question_contract
    keys = frozenset(point.key for point in contract.required_points)
    covered = tuple(point.key for point in candidate.covered_points)
    _references(covered, keys, "covered_points")
    _references(candidate.missing_points, keys, "missing_points")
    if candidate.sufficiency is None:
        if not candidate.limitations:
            raise ContractError("semantic", "unevaluable sufficiency")
    elif set(covered) | set(candidate.missing_points) != keys:
        raise ContractError("semantic", "point coverage")
    if candidate.evaluation_status != "evaluated" and not candidate.limitations:
        raise ContractError("semantic", "evaluation limitations")
    if candidate.evaluation_status == "not_evaluable" and candidate.sufficiency is not None:
        raise ContractError("semantic", "evaluation_status")
    if candidate.sufficiency == "sufficient" and candidate.missing_points:
        raise ContractError("semantic", "sufficiency")
    if candidate.sufficiency in ("partial", "insufficient") and not candidate.missing_points:
        raise ContractError("semantic", "missing points required")
    if candidate.sufficiency == "partial" and not covered:
        raise ContractError("semantic", "partial coverage required")
    if set(covered).intersection(candidate.missing_points) and not candidate.limitations:
        raise ContractError("semantic", "partially covered point limitations")
    for point in candidate.covered_points:
        if not point.answer_quotes:
            raise ContractError("semantic", "covered point quotes")
        _quotes(point.answer_quotes, answer_text)
    technical = candidate.technical_assessment
    _quotes(technical.answer_quotes, answer_text)
    _references(technical.evidence_refs, evidence_refs, "technical evidence")
    contribution = candidate.contribution_scope
    _quotes(contribution.answer_quotes, answer_text)
    if contribution.scope != "unknown" and not contribution.answer_quotes:
        raise ContractError("semantic", "contribution quotes")
    if contribution.scope == "unknown" and not (
        contribution.answer_quotes or candidate.limitations
    ):
        raise ContractError("semantic", "contribution limitations")
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
    # 허용 Persona와 종료 권한은 Controller 입력이며 모델의 제안으로 확장하지 않는다.
    _convert(DirectorDecision, candidate, "decision", wire=False)
    _convert(tuple[PersonaId, ...], allowed_personas, "allowed_personas", wire=False)
    if type(finish_allowed) is not bool:
        raise ContractError("schema", "finish_allowed")
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


@dataclass(frozen=True)
class Evidence(_Contract):
    evidence_id: str | None
    repository_id: str | None
    git_ref: str | None
    source_kind: str
    path: str | None
    metadata_key: str | None
    content: str
    tool_name: str | None
    summary: str | None = None
    start_line: int | None = None
    end_line: int | None = None

    def __post_init__(self) -> None:
        super().__post_init__()
        if (self.repository_id is None) != (self.git_ref is None):
            raise ContractError("semantic", "repository ref")
        if self.git_ref is not None:
            _sha(self.git_ref)
        if (self.path is None) == (self.metadata_key is None):
            raise ContractError("semantic", "evidence location")
        if self.path is not None:
            if self.repository_id is None:
                raise ContractError("semantic", "source repository ref")
            _repository_path(self.path)
        if (self.start_line is None) != (self.end_line is None):
            raise ContractError("semantic", "line range")
        if self.start_line is not None:
            if self.metadata_key is not None:
                raise ContractError("semantic", "metadata line range")
            _positive_int(self.start_line, "start_line")
            _positive_int(self.end_line, "end_line")
            if self.start_line > cast(int, self.end_line):
                raise ContractError("semantic", "line range")


@dataclass(frozen=True)
class ToolResult(_Contract):
    status: Literal["found", "not_found", "insufficient_analysis", "tool_error"]
    items: tuple[Evidence, ...]
    searched_scope: tuple[str, ...]
    limitations: tuple[str, ...]
    error_code: str | None

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.status in ("found", "not_found") and not self.searched_scope:
            raise ContractError("semantic", "searched_scope")
        if self.status == "found" and (not self.items or self.error_code is not None):
            raise ContractError("semantic", "found result")
        if self.status in ("not_found", "insufficient_analysis") and (
            self.items or self.error_code is not None
        ):
            raise ContractError("semantic", "empty result")
        if self.status == "tool_error" and (self.error_code is None or not self.limitations):
            raise ContractError("semantic", "tool error")
        if self.status == "insufficient_analysis" and not self.limitations:
            raise ContractError("semantic", "analysis limitations")


@dataclass(frozen=True)
class PersonaCount(_Contract):
    persona: PersonaId
    count: int

    def __post_init__(self) -> None:
        super().__post_init__()
        _positive_int(self.count, "persona count", allow_zero=True)


@dataclass(frozen=True)
class JDRequirement(_Contract):
    id: str
    text: str
    requirement_type: Literal["required", "preferred", "unknown"]
    source_field: str
    tech_tags: tuple[str, ...]


@dataclass(frozen=True)
class ContextRepository(_Contract):
    repository_id: str
    git_ref: str
    primary: bool
    analysis_refs: tuple[str, ...]
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        super().__post_init__()
        _sha(self.git_ref)
        _unique(cast(tuple[object, ...], self.analysis_refs), "analysis_refs")


@dataclass(frozen=True)
class HistoryTurn(_Contract):
    turn_id: str
    persona: PersonaId
    question: str
    answer: str
    analysis_ref: str | None


@dataclass(frozen=True)
class DomainFrame(_Contract):
    id: str
    category: str
    version: str
    text: str


@dataclass(frozen=True)
class ContextLimits(_Contract):
    remaining_calls: int
    remaining_replans: int
    policy_version: str

    def __post_init__(self) -> None:
        super().__post_init__()
        _positive_int(self.remaining_calls, "remaining_calls", allow_zero=True)
        _positive_int(self.remaining_replans, "remaining_replans", allow_zero=True)


@dataclass(frozen=True)
class Context(_Contract):
    interview_id: str
    current_turn_id: str | None
    turn_no: int
    total_turns: int
    persona_counts: tuple[PersonaCount, ...]
    allowed_personas: tuple[PersonaId, ...]
    jd_requirements: tuple[JDRequirement, ...]
    repositories: tuple[ContextRepository, ...]
    history: tuple[HistoryTurn, ...]
    current_question_contract: QuestionContract | None
    evidence: tuple[Evidence, ...]
    domain_frames: tuple[DomainFrame, ...]
    limits: ContextLimits

    def __post_init__(self) -> None:
        super().__post_init__()
        _positive_int(self.turn_no, "turn_no")
        if self.total_turns != 9 or self.turn_no > self.total_turns:
            raise ContractError("semantic", "turn range")
        _unique(tuple(item.persona for item in self.persona_counts), "persona_counts")
        _unique(cast(tuple[object, ...], self.allowed_personas), "allowed_personas")


def _sha(value: str) -> None:
    if fullmatch(r"[0-9a-f]{40}", value) is None:
        raise ContractError("schema", "head_sha")


def _repository_path(value: str) -> None:
    if (
        value.startswith("/")
        or "\\" in value
        or any(part in ("", ".", "..") for part in value.split("/"))
    ):
        raise ContractError("schema", "path")


@dataclass(frozen=True)
class LanguageBytes(_Contract):
    name: str
    bytes: int

    def __post_init__(self) -> None:
        super().__post_init__()
        _positive_int(self.bytes, "language bytes", allow_zero=True)


@dataclass(frozen=True)
class ShallowRepoInput(_Contract):
    repository_id: str
    head_sha: str
    description: str | None
    readme_text: str | None
    readme_truncated: bool
    languages: tuple[LanguageBytes, ...]
    commit_count: int | None
    user_commit_count: int | None
    collection_errors: tuple[str, ...]

    def __post_init__(self) -> None:
        super().__post_init__()
        _sha(self.head_sha)
        _unique(tuple(item.name for item in self.languages), "languages")
        _unique(cast(tuple[object, ...], self.collection_errors), "collection_errors")
        for name in ("commit_count", "user_commit_count"):
            value = getattr(self, name)
            if value is not None:
                _positive_int(value, name, allow_zero=True)


@dataclass(frozen=True)
class ShallowBasis(_Contract):
    kind: Literal["readme", "description", "languages", "commit_metadata"]
    claim: str


@dataclass(frozen=True)
class ShallowRepoAnalysis(_Contract):
    repository_id: str
    head_sha: str
    purpose: str
    key_features: tuple[str, ...]
    project_types: tuple[str, ...]
    tech_stack: tuple[str, ...]
    project_role_summary: str
    basis: tuple[ShallowBasis, ...]
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        super().__post_init__()
        _sha(self.head_sha)
        if not self.basis:
            raise ContractError("schema", "basis")
        _unique(cast(tuple[object, ...], self.basis), "basis")
        for name in ("key_features", "project_types", "tech_stack", "limitations"):
            _unique(cast(tuple[object, ...], getattr(self, name)), name)


@dataclass(frozen=True)
class RepoItemFailure(_Contract):
    repository_id: str | None
    head_sha: str | None
    stage: FailureStage
    reason_summary: str


@dataclass(frozen=True)
class ShallowBatchResult(_Contract):
    succeeded: tuple[ShallowRepoAnalysis, ...]
    failed: tuple[RepoItemFailure, ...]


def validate_shallow_batch(
    inputs: tuple[ShallowRepoInput, ...],
    candidates: tuple[ShallowRepoAnalysis, ...],
) -> ContractChecked[ShallowBatchResult]:
    # 응답 순서가 바뀌어도 입력 저장소 ID와 고정 SHA를 기준으로 결과를 결합한다.
    _convert(tuple[ShallowRepoInput, ...], inputs, "inputs", wire=False)
    _convert(tuple[ShallowRepoAnalysis, ...], candidates, "candidates", wire=False)
    input_ids = tuple(item.repository_id for item in inputs)
    _unique(cast(tuple[object, ...], input_ids), "input repository ids")
    counts = {repository_id: 0 for repository_id in input_ids}
    unknown: list[RepoItemFailure] = []
    for item in candidates:
        if item.repository_id in counts:
            counts[item.repository_id] += 1
        else:
            unknown.append(
                RepoItemFailure(
                    item.repository_id,
                    item.head_sha,
                    "semantic",
                    "unregistered repository_id",
                )
            )
    by_id = {candidate.repository_id: candidate for candidate in candidates}
    succeeded: list[ShallowRepoAnalysis] = []
    failed: list[RepoItemFailure] = []
    for source in inputs:
        candidate = by_id.get(source.repository_id)
        reason = None
        if counts[source.repository_id] == 0:
            reason = "missing repository result"
        elif counts[source.repository_id] > 1:
            reason = "duplicate repository result"
        elif candidate is not None and candidate.head_sha != source.head_sha:
            reason = "head_sha mismatch"
        elif (
            candidate is not None
            and (source.collection_errors or source.readme_truncated)
            and not candidate.limitations
        ):
            reason = "collection limitations missing"
        elif candidate is not None:
            available = {
                "readme": source.readme_text is not None,
                "description": source.description is not None,
                "languages": bool(source.languages),
                "commit_metadata": (
                    source.commit_count is not None or source.user_commit_count is not None
                ),
            }
            if any(not available[item.kind] for item in candidate.basis):
                reason = "analysis basis unavailable"
        if reason is None and candidate is not None:
            succeeded.append(candidate)
        else:
            failed.append(
                RepoItemFailure(
                    source.repository_id, source.head_sha, "semantic", cast(str, reason)
                )
            )
    return _checked(ShallowBatchResult(tuple(succeeded), tuple(failed + unknown)))


def parse_shallow_batch(
    payload: object, *, inputs: tuple[ShallowRepoInput, ...]
) -> ContractChecked[ShallowBatchResult]:
    """L1 항목을 개별 해석하여 일부 schema 실패가 다른 정상 결과를 지우지 않게 한다."""
    if type(payload) is not list:
        raise ContractError("schema", "shallow batch")
    _convert(tuple[ShallowRepoInput, ...], inputs, "inputs", wire=False)
    input_by_id = {item.repository_id: item for item in inputs}
    if len(input_by_id) != len(inputs):
        raise ContractError("semantic", "input repository ids")
    entries_by_id: dict[str, list[object]] = {}
    failures: list[RepoItemFailure] = []
    for item in payload:
        repository_id = item.get("repository_id") if type(item) is dict else None
        head_sha = item.get("head_sha") if type(item) is dict else None
        if type(repository_id) is not str or not repository_id.strip():
            # ID가 없는 오류를 임의 저장소에 배정하면 잘못된 항목을 재요청하게 된다.
            failures.append(
                RepoItemFailure(
                    None,
                    head_sha if type(head_sha) is str and head_sha.strip() else None,
                    "schema",
                    "invalid field: repository_id",
                )
            )
            continue
        entries_by_id.setdefault(repository_id, []).append(item)

    succeeded: list[ShallowRepoAnalysis] = []
    for source in inputs:
        entries = entries_by_id.get(source.repository_id, [])
        if not entries:
            failures.append(
                RepoItemFailure(
                    source.repository_id,
                    source.head_sha,
                    "semantic",
                    "missing repository result",
                )
            )
            continue
        if len(entries) > 1:
            failures.append(
                RepoItemFailure(
                    source.repository_id,
                    source.head_sha,
                    "semantic",
                    "duplicate repository result",
                )
            )
            continue
        item = entries[0]
        assert type(item) is dict
        try:
            _text(item.get("head_sha"), "head_sha")
            _sha(cast(str, item["head_sha"]))
            if item["head_sha"] != source.head_sha:
                raise ContractError("semantic", "head_sha mismatch")
            candidate = decode(ShallowRepoAnalysis, item)
        except ContractError as error:
            failures.append(
                RepoItemFailure(
                    source.repository_id,
                    source.head_sha,
                    error.stage,
                    f"invalid field: {error.field}",
                )
            )
            continue
        checked = validate_shallow_batch((source,), (candidate,)).data
        succeeded.extend(checked.succeeded)
        failures.extend(checked.failed)

    for repository_id, entries in entries_by_id.items():
        if repository_id in input_by_id:
            continue
        head_sha = entries[0].get("head_sha") if type(entries[0]) is dict else None
        failures.append(
            RepoItemFailure(
                repository_id,
                head_sha if type(head_sha) is str and head_sha.strip() else None,
                "semantic",
                "unregistered repository_id",
            )
        )
    return _checked(ShallowBatchResult(tuple(succeeded), tuple(failures)))


@dataclass(frozen=True)
class SourceDocument(_Contract):
    path: str
    kind: Literal["file", "directory"]
    content: str
    read_scope: str

    def __post_init__(self) -> None:
        super().__post_init__()
        _repository_path(self.path)


@dataclass(frozen=True)
class DeepRepoInput(_Contract):
    repository_id: str
    head_sha: str
    shallow: ShallowRepoAnalysis
    sources: tuple[SourceDocument, ...]

    def __post_init__(self) -> None:
        super().__post_init__()
        _sha(self.head_sha)
        if (
            self.shallow.repository_id != self.repository_id
            or self.shallow.head_sha != self.head_sha
        ):
            raise ContractError("semantic", "shallow repository ref")
        _unique(tuple(source.path for source in self.sources), "source paths")


@dataclass(frozen=True)
class NotableArea(_Contract):
    path: str
    observation: str
    scope: str
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        super().__post_init__()
        _repository_path(self.path)


@dataclass(frozen=True)
class DeepRepoAnalysis(_Contract):
    repository_id: str
    head_sha: str
    architecture_summary: str
    confirmed_technologies: tuple[str, ...]
    notable_areas: tuple[NotableArea, ...]
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        super().__post_init__()
        _sha(self.head_sha)
        _unique(cast(tuple[object, ...], self.confirmed_technologies), "confirmed technologies")


def validate_deep_analysis(
    candidate: DeepRepoAnalysis, *, source: DeepRepoInput
) -> ContractChecked[DeepRepoAnalysis]:
    _convert(DeepRepoAnalysis, candidate, "deep analysis", wire=False)
    _convert(DeepRepoInput, source, "deep input", wire=False)
    if candidate.repository_id != source.repository_id or candidate.head_sha != source.head_sha:
        raise ContractError("semantic", "repository ref")
    if not 1 <= len(candidate.notable_areas) <= 5:
        raise ContractError("semantic", "notable area count")
    _unique(tuple(area.path for area in candidate.notable_areas), "notable area paths")
    source_by_path = {item.path: item for item in source.sources}
    for area in candidate.notable_areas:
        matched = source_by_path.get(area.path)
        if matched is None or matched.read_scope != area.scope:
            raise ContractError("semantic", "notable area source scope")
    return _checked(candidate)


def _json_value(value: object) -> object:
    if is_dataclass(value) and isinstance(value, _Contract):
        return {field.name: _json_value(getattr(value, field.name)) for field in fields(value)}
    if type(value) is tuple:
        return [_json_value(item) for item in value]
    if value is None or type(value) in (str, int, bool, float):
        return value
    raise ContractError("schema", "serializable contract data")


def to_data[T](value: ContractChecked[T]) -> dict[str, object]:
    """계약 검증을 통과한 값만 직렬화하여 원시 후보가 저장 경계로 넘어가지 않게 한다."""
    if type(value) is not ContractChecked:
        raise ContractError("schema", "contract checked input")
    data = _json_value(value.data)
    if type(data) is not dict:
        raise ContractError("schema", "contract object")
    return cast(dict[str, object], data)
