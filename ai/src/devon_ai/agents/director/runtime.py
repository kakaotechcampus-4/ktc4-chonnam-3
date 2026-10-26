"""목적·질문을 함께 제안하고 별도 모델 시도로 검토하는 단일 Director 실행 경로."""

from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, fields
from typing import Protocol, cast

from devon_ai import contracts as c
from devon_ai.agents.director.agent import _RECOVERY_CODES, _object_schema, _references

type Location = tuple[str, str, str]


class DirectorModelCall(Protocol):
    async def __call__[T](
        self, request: c.ModelRequest, validator: Callable[[object], T]
    ) -> c.ModelResult[T]: ...


@dataclass(frozen=True)
class DirectorOutcome:
    decision: c.ContractChecked[c.DirectorDecision]
    question: c.ContractChecked[c.Question] | None
    generation: c.AttemptMetadata | None


@dataclass(frozen=True)
class _Plan:
    question: c.Question
    intent: str
    reason_summary: str


def _plan_schema() -> dict[str, object]:
    text = {"type": "string"}
    texts = {"type": "array", "items": text}
    contract = _object_schema(
        {
            "purpose": text,
            "required_points": {
                "type": "array",
                "items": _object_schema({"key": text, "description": text}),
            },
            "assumptions": texts,
            "basis_refs": {
                "type": "array",
                "items": _object_schema(
                    {
                        "kind": {
                            "type": "string",
                            "enum": [
                                "evidence",
                                "jd_requirement",
                                "job_posting",
                                "answer_turn",
                            ],
                        },
                        "id": text,
                    }
                ),
            },
            "evaluation_scope": text,
        }
    )
    question = _object_schema(
        {
            "persona": {"type": "string", "enum": ["hr_manager", "tech_lead", "domain_lead"]},
            "text": text,
            "topic_code": text,
            "question_contract": contract,
            "evidence_refs": texts,
            "jd_requirement_ids": texts,
        }
    )
    return _object_schema({"question": question, "intent": text, "reason_summary": text})


_REVIEW_CHECKS = (
    "plan_valid",
    "context_valid",
    "wording_valid",
    "contract_matches",
    "safe_alternative",
)


def _review_schema() -> dict[str, object]:
    return _object_schema(
        {
            **{key: {"type": "boolean"} for key in _REVIEW_CHECKS},
            "reason_summary": {"type": "string"},
        }
    )


def _plan_object(raw: object, expected: set[str], name: str) -> dict[str, object]:
    if type(raw) is not dict or set(raw) != expected:
        raise c.ContractError("schema", name)
    return cast(dict[str, object], raw)


def _plan_question(raw: object) -> c.Question:
    # 공통 decode의 부가 필드 무시 정책을 바꾸지 않고 새 planner의 중첩 출력만 엄격히 검사한다.
    question = _plan_object(raw, {item.name for item in fields(c.Question)}, "Question")
    contract = _plan_object(
        question["question_contract"],
        {item.name for item in fields(c.QuestionContract)},
        "QuestionContract",
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


def _validate_candidate(
    candidate: c.Question,
    context: c.Context,
    sources: Mapping[c.BasisRef, str],
) -> c.Question:
    return c.validate_question_candidate(
        candidate,
        allowed_personas=context.allowed_personas,
        evidence_refs=frozenset(
            ref.id for ref in candidate.question_contract.basis_refs if ref.kind == "evidence"
        ),
        basis_refs=frozenset(sources),
        jd_requirement_ids=frozenset(
            ref.id for ref in candidate.question_contract.basis_refs if ref.kind == "jd_requirement"
        ),
    )


def _assessment(raw: object, candidate: c.Question) -> c.QuestionReview | c.CandidateRecovery:
    if type(raw) is not dict or set(raw) != {*_REVIEW_CHECKS, "reason_summary"}:
        raise c.ContractError("schema", "DirectorReview")
    if any(type(raw[key]) is not bool for key in _REVIEW_CHECKS):
        raise c.ContractError("schema", "review checks")
    reason = raw["reason_summary"]
    if type(reason) is not str or not reason.strip():
        raise c.ContractError("schema", "review reason")
    if all(raw[key] for key in _REVIEW_CHECKS[:-1]):
        return c.QuestionReview(candidate.text, candidate.question_contract)
    if not raw["safe_alternative"]:
        return c.CandidateRecovery("no_valid_candidate", reason)
    if not raw["plan_valid"] or not raw["context_valid"]:
        return c.CandidateRecovery("replan", reason)
    return c.CandidateRecovery("rewrite", reason)


def _input_payload(
    context: c.Context,
    prompt: c.PromptSpec,
    limits: c.CallLimits,
    answer_analysis: c.ContractChecked[c.AnswerAnalysis] | None,
    reference_texts: Mapping[c.BasisRef, str] | None,
    prior_analyses: Mapping[str, c.ContractChecked[c.AnswerAnalysis]] | None,
    tool_results: tuple[c.ToolResult, ...],
) -> tuple[dict[str, object], dict[c.BasisRef, str]]:
    if type(context) is not c.Context:
        raise c.ContractError("schema", "Director context")
    if type(prompt) is not c.PromptSpec or prompt.task_name != "director":
        raise c.ContractError("schema", "Director prompt")
    if type(limits) is not c.CallLimits:
        raise c.ContractError("schema", "Director limits")
    if type(tool_results) is not tuple or any(
        type(item) is not c.ToolResult for item in tool_results
    ):
        raise c.ContractError("schema", "Director tool results")
    if not context.allowed_personas:
        raise c.ContractError("semantic", "question not allowed")
    if context.turn_no == 1 and (
        context.allowed_personas != ("hr_manager",)
        or context.current_turn_id is not None
        or context.current_question_contract is not None
        or context.history
        or any(item.count for item in context.persona_counts)
        or answer_analysis is not None
    ):
        raise c.ContractError("semantic", "first HR question")
    analysis = None
    if answer_analysis is not None:
        if (
            type(answer_analysis) is not c.ContractChecked
            or type(answer_analysis.data) is not c.AnswerAnalysis
        ):
            raise c.ContractError("schema", "checked analysis")
        analysis = c.to_data(answer_analysis)
    if reference_texts is not None and not isinstance(reference_texts, Mapping):
        raise c.ContractError("schema", "source text mapping")
    sources = _references(context, {} if reference_texts is None else reference_texts)
    previous: dict[str, object] = {}
    if prior_analyses is not None:
        if not isinstance(prior_analyses, Mapping):
            raise c.ContractError("schema", "prior analyses")
        history_ids = {turn.turn_id for turn in context.history}
        for turn_id, checked in prior_analyses.items():
            if type(turn_id) is not str or turn_id not in history_ids:
                raise c.ContractError("semantic", "prior analysis turn")
            if type(checked) is not c.ContractChecked or type(checked.data) is not c.AnswerAnalysis:
                raise c.ContractError("schema", "checked prior analysis")
            previous[turn_id] = c.to_data(checked)
    return {
        "context": asdict(context),
        "reference_texts": [
            {"kind": ref.kind, "id": ref.id, "text": text} for ref, text in sources.items()
        ],
        "answer_analysis": analysis,
        "prior_analyses": previous,
        "tool_results": [asdict(result) for result in tool_results],
    }, sources


async def run_director(
    context: c.Context,
    *,
    prompt: c.PromptSpec,
    limits: c.CallLimits,
    model_call: DirectorModelCall,
    answer_analysis: c.ContractChecked[c.AnswerAnalysis] | None = None,
    reference_texts: Mapping[c.BasisRef, str] | None = None,
    prior_analyses: Mapping[str, c.ContractChecked[c.AnswerAnalysis]] | None = None,
    tool_results: tuple[c.ToolResult, ...] = (),
) -> c.ModelResult[DirectorOutcome]:
    """목적·계약·초안을 한 번 생성하고 남은 한 번으로 독립 검토한다.

    두 요청은 BE가 주입한 동일 CallBudget을 사용하며 각각 한 시도만 허용한다.
    생성자 자기검토·정당화는 검토 입력에서 제외한다. 거절 후 재생성하지 않으며
    취소·프로그래밍 오류는 상위로 전파한다. 종료 권한과 저장·Tool 실행은 BE 책임이다.
    """
    try:
        payload, sources = _input_payload(
            context,
            prompt,
            limits,
            answer_analysis,
            reference_texts,
            prior_analyses,
            tool_results,
        )
    except c.ContractError as exc:
        return c.ModelResult(
            None,
            c.CallFailure(
                exc.stage,
                "director_input_invalid",
                "Director input rejected.",
            ),
            (),
        )
    if context.limits.remaining_calls < 2:
        return c.ModelResult(
            None,
            c.CallFailure(
                "budget",
                "llm_failed",
                "Generation and independent review require two attempts.",
            ),
            (),
        )

    def validate_plan(raw: object) -> _Plan:
        if type(raw) is not dict or set(raw) != {"question", "intent", "reason_summary"}:
            raise c.ContractError("schema", "DirectorPlan")
        candidate = _validate_candidate(_plan_question(raw["question"]), context, sources)
        # 자유 텍스트인 의도·사유도 기존 결정 계약의 타입 검사로 검증한다.
        proposal = c.DirectorDecision(
            "ask",
            raw["intent"],
            candidate.persona,
            candidate.question_contract.purpose,
            (),
            raw["reason_summary"],
        )
        return _Plan(candidate, proposal.intent, proposal.reason_summary)

    generated = await model_call(
        c.ModelRequest(
            prompt,
            {**payload, "operation": "plan"},
            "DirectorPlan",
            "director-plan.v1",
            _plan_schema(),
            limits,
            max_attempts=1,
        ),
        validate_plan,
    )
    if generated.failure is not None:
        return c.ModelResult(None, generated.failure, generated.attempts)
    plan = generated.data
    if type(plan) is not _Plan:
        raise TypeError("ModelCall did not return a validated Director plan")
    try:
        _validate_candidate(plan.question, context, sources)
    except c.ContractError as exc:
        return c.ModelResult(
            None,
            c.CallFailure(
                exc.stage,
                "director_candidate_invalid",
                "Question candidate rejected.",
            ),
            generated.attempts,
        )

    reviewed = await model_call(
        c.ModelRequest(
            prompt,
            {
                **payload,
                "operation": "review",
                "question": asdict(plan.question),
                "intent": plan.intent,
            },
            "DirectorReview",
            "director-review.v1",
            _review_schema(),
            limits,
            max_attempts=1,
        ),
        lambda raw: _assessment(raw, plan.question),
    )
    attempts = generated.attempts + reviewed.attempts
    if reviewed.failure is not None:
        return c.ModelResult(None, reviewed.failure, attempts)
    assessment = reviewed.data
    if type(assessment) is c.CandidateRecovery:
        return c.ModelResult(
            None,
            c.CallFailure(
                "semantic",
                _RECOVERY_CODES[assessment.recovery],
                "Independent question review rejected.",
            ),
            attempts,
        )
    try:
        checked = c.validate_question(
            plan.question,
            review=cast(c.QuestionReview, assessment),
            allowed_personas=context.allowed_personas,
            evidence_refs=frozenset(
                ref.id
                for ref in plan.question.question_contract.basis_refs
                if ref.kind == "evidence"
            ),
            basis_refs=frozenset(sources),
            jd_requirement_ids=frozenset(
                ref.id
                for ref in plan.question.question_contract.basis_refs
                if ref.kind == "jd_requirement"
            ),
        )
        decision = c.validate_decision(
            c.DirectorDecision(
                "ask",
                plan.intent,
                plan.question.persona,
                plan.question.question_contract.purpose,
                (),
                plan.reason_summary,
            ),
            question=checked,
            allowed_personas=context.allowed_personas,
            finish_allowed=False,
            allowed_locations=frozenset(),
        )
    except c.ContractError as exc:
        return c.ModelResult(
            None,
            c.CallFailure(
                exc.stage,
                "director_review_failed",
                "Independent question review rejected.",
            ),
            attempts,
        )
    return c.ModelResult(DirectorOutcome(decision, checked, generated.attempts[-1]), None, attempts)


def verification_decision(
    context: c.Context,
    analysis: c.ContractChecked[c.AnswerAnalysis],
    *,
    allowed_locations: frozenset[Location],
) -> c.ContractChecked[c.DirectorDecision] | None:
    """현재 T3의 명시적 필요·영향 판단에서 허용된 추가 조회만 제안한다.

    기존 근거가 충분하다고 분석한 주장은 제외한다. 원문 의미의 충분성과 현재
    판단에 대한 영향은 검증된 T3의 요청·목적에 의존한다. 조회·감점·종료는 하지 않는다.
    """
    if type(context) is not c.Context:
        raise c.ContractError("schema", "Director context")
    if type(analysis) is not c.ContractChecked or type(analysis.data) is not c.AnswerAnalysis:
        raise c.ContractError("schema", "checked analysis")
    if type(allowed_locations) is not frozenset:
        raise c.ContractError("schema", "allowed locations")
    repositories = {repo.repository_id: repo.git_ref for repo in context.repositories}
    for location in allowed_locations:
        if (
            type(location) is not tuple
            or len(location) != 3
            or repositories.get(location[0]) != location[1]
        ):
            raise c.ContractError("semantic", "allowed location ref")
    value = analysis.data
    if not value.needs_verification:
        return None
    registered = frozenset(ref.id for ref in _references(context, {}) if ref.kind == "evidence")
    supported = {
        claim.claim_text
        for claim in value.claim_checks
        if claim.status == "supported"
        and claim.evidence_refs
        and set(claim.evidence_refs).issubset(registered)
    }
    requests = tuple(
        request for request in value.verification_requests if request.claim_text not in supported
    )
    if not requests:
        return None
    return c.validate_decision(
        c.DirectorDecision(
            "retrieve",
            "현재 주장을 원문으로 확인",
            None,
            requests[0].claim_text,
            requests,
            " ".join(request.purpose for request in requests),
        ),
        question=None,
        allowed_personas=context.allowed_personas,
        finish_allowed=False,
        allowed_locations=allowed_locations,
    )
