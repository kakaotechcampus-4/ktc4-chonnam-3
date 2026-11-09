"""목적·질문을 함께 제안하고 별도 모델 시도로 검토하는 단일 Director 실행 경로."""

import json
from collections.abc import Callable, Mapping
from dataclasses import MISSING, asdict, dataclass, field, fields
from typing import Any, Protocol, cast, get_args

from devon_ai import contracts as c
from devon_ai.agents.director.agent import (
    _RECOVERY_CODES,
    _model_reference_texts,
    _object_schema,
    _references,
)

SUPPORTED_PROMPT_VERSIONS = frozenset(
    {
        "director_v5",
        "director_v2",
        "director_v4",
        "director_v1",
        "director_v7",
        "director_v8",
        "director_v6",
        "director_v3",
    }
)


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
class RecoveryFeedback:
    """직전 생성·반려 이력이다. 원문·정답·승인 또는 허용 참조가 아니다."""

    previous_candidate: c.Question = field(repr=False)
    recovery: c.CandidateRecovery = field(repr=False)

    def __post_init__(self) -> None:
        _feedback_payload(self)


def _feedback_payload(feedback: RecoveryFeedback) -> dict[str, object]:
    if (
        type(feedback) is not RecoveryFeedback
        or type(feedback.previous_candidate) is not c.Question
        or type(feedback.recovery) is not c.CandidateRecovery
    ):
        raise c.ContractError("schema", "Director recovery feedback")
    candidate = _plan_question(json.loads(json.dumps(asdict(feedback.previous_candidate))))
    recovery = c.decode_strict(c.CandidateRecovery, asdict(feedback.recovery))
    payload: dict[str, object] = {
        "version": "director-recovery.v1",
        "previous_candidate": asdict(candidate),
        "recovery": recovery.recovery,
        "review_reason_summary": recovery.reason_summary,
    }
    if len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) > 16384:
        raise c.ContractError("schema", "Director recovery feedback size")
    return payload


def _feedback_json(raw: str) -> object:
    def pairs(items: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate feedback key")
            result[key] = value
        return result

    def invalid_constant(value: str) -> object:
        raise ValueError("invalid feedback constant")

    if len(raw.encode("utf-8")) > 131072:
        raise ValueError("feedback raw size")
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid_constant)


def recovery_feedback_from_attempts(
    attempts: object, *, failure_code: str
) -> RecoveryFeedback | None:
    """저장된 두 원시 시도를 엄격히 복원한다. 불명확한 이력은 자동 복구 근거로 쓰지 않는다."""
    if type(attempts) not in (list, tuple) or failure_code not in _RECOVERY_CODES.values():
        return None
    items = cast(list[object] | tuple[object, ...], attempts)
    if len(items) != 2:
        return None
    try:
        records = []
        for item in items:
            if type(item) is c.AttemptMetadata:
                item.__post_init__()
                records.append(item)
                continue
            # AttemptMetadata는 _Contract가 아니므로 필드 집합과 생성자 검증을 사용한다.
            data = _plan_object(
                item,
                {entry.name for entry in fields(c.AttemptMetadata)},
                "recovery attempt metadata",
                frozenset(
                    entry.name
                    for entry in fields(c.AttemptMetadata)
                    if entry.default is not MISSING
                ),
            )
            records.append(c.AttemptMetadata(**cast(dict[str, Any], data)))
        generated, reviewed = records
        if (
            generated.schema_version
            not in {"director-plan.v1", "director-plan.v2", "director-plan.v3"}
            or reviewed.schema_version != "director-review.v1"
            or (generated.attempt, reviewed.attempt) != (1, 2)
            or (generated.provider, generated.model, generated.prompt_version)
            != (reviewed.provider, reviewed.model, reviewed.prompt_version)
            or any(item.error_stage is not None or item.error_code is not None for item in records)
            or generated.raw_output is None
            or reviewed.raw_output is None
        ):
            return None
        raw = _plan_object(
            _feedback_json(generated.raw_output),
            {"question", "intent", "reason_summary"},
            "DirectorPlan",
        )
        candidate = _plan_question(raw["question"])
        c.DirectorDecision(
            "ask",
            cast(str, raw["intent"]),
            candidate.persona,
            candidate.question_contract.purpose,
            (),
            cast(str, raw["reason_summary"]),
        )
        assessment = _assessment(_feedback_json(reviewed.raw_output), candidate)
        if (
            type(assessment) is not c.CandidateRecovery
            or _RECOVERY_CODES[assessment.recovery] != failure_code
        ):
            return None
        return RecoveryFeedback(candidate, assessment)
    except (c.ContractError, ValueError, TypeError, RecursionError):
        return None


@dataclass(frozen=True)
class _Plan:
    question: c.Question
    intent: str
    reason_summary: str


def _plan_schema(coverage: bool = False) -> dict[str, object]:
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
                            "enum": list(get_args(c.BasisKind)),
                        },
                        "id": text,
                    }
                ),
            },
            "evaluation_scope": text,
        }
    )
    if coverage:
        cast(dict[str, object], contract["properties"])["evaluation_keys"] = {
            "type": "array",
            "items": {"type": "string", "enum": list(get_args(c.ScoreKeyId))},
        }
        cast(list[str], contract["required"]).append("evaluation_keys")
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
    if coverage:
        cast(dict[str, object], question["properties"]).update(
            {
                "question_type": {"type": "string", "enum": ["main", "follow_up"]},
                "parent_turn_id": {"type": ["string", "null"]},
            }
        )
        cast(list[str], question["required"]).extend(("question_type", "parent_turn_id"))
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


def _bounded_plan_schema(
    context: c.Context, sources: Mapping[c.BasisRef, str], coverage: bool
) -> dict[str, object]:
    """v6에서만 실제 입력의 식별자를 선택하게 한다. 기존 버전 스키마는 보존한다."""
    schema = _plan_schema(coverage)
    question = cast(dict[str, object], cast(dict[str, object], schema["properties"])["question"])
    props = cast(dict[str, object], question["properties"])
    contract = cast(dict[str, object], props["question_contract"])
    contract_props = cast(dict[str, object], contract["properties"])
    grouped: dict[str, list[str]] = {}
    for ref in sorted(sources, key=lambda item: (item.kind, item.id)):
        grouped.setdefault(ref.kind, []).append(ref.id)

    def identifiers(kind: str) -> dict[str, object]:
        values = grouped.get(kind, [])
        if not values:
            # 빈 enum 대신 빈 배열만 허용해 공급자 스키마의 유효성도 유지한다.
            return {"type": "array", "items": {"type": "string"}, "maxItems": 0}
        return {"type": "array", "items": {"type": "string", "enum": values}}

    props["persona"] = {"type": "string", "enum": list(context.allowed_personas)}
    props["evidence_refs"] = identifiers("evidence")
    props["jd_requirement_ids"] = identifiers("jd_requirement")
    if grouped:
        contract_props["basis_refs"] = {
            "type": "array",
            "items": {
                "anyOf": [
                    _object_schema(
                        {
                            "kind": {"type": "string", "enum": [kind]},
                            "id": {"type": "string", "enum": values},
                        }
                    )
                    for kind, values in grouped.items()
                ]
            },
        }
    else:
        cast(dict[str, object], contract_props["basis_refs"])["maxItems"] = 0
    props["question_type"] = {"type": "string", "enum": ["main", "follow_up"]}
    props["parent_turn_id"] = {
        "type": ["string", "null"],
        "enum": [None, *(turn.turn_id for turn in context.history)],
    }
    required = cast(list[str], question["required"])
    required.extend(name for name in ("question_type", "parent_turn_id") if name not in required)
    return schema


def _plan_object(
    raw: object, expected: set[str], name: str, optional: frozenset[str] = frozenset()
) -> dict[str, object]:
    if type(raw) is not dict or not expected - optional <= set(raw) <= expected:
        raise c.ContractError("schema", name)
    return cast(dict[str, object], raw)


def _plan_question(raw: object) -> c.Question:
    # 공통 decode의 부가 필드 무시 정책을 바꾸지 않고 새 planner의 중첩 출력만 엄격히 검사한다.
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


def _validate_candidate(
    candidate: c.Question,
    context: c.Context,
    sources: Mapping[c.BasisRef, str],
    coverage: bool = False,
) -> c.Question:
    c.validate_question_candidate(
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
    if candidate.parent_turn_id is not None:
        parent = next(
            (item for item in context.history if item.turn_id == candidate.parent_turn_id), None
        )
        if parent is None or parent.persona != candidate.persona:
            raise c.ContractError("semantic", "question parent")
    if coverage:
        expected = next(
            (item.keys for item in context.evaluation_targets if item.persona == candidate.persona),
            (),
        )
        if not expected or set(candidate.question_contract.evaluation_keys) != set(expected):
            raise c.ContractError("semantic", "question evaluation keys")
        if "company_job_fit" in expected and not candidate.jd_requirement_ids:
            raise c.ContractError("semantic", "job fit JD references")
    return candidate


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


def _turn_state(context: c.Context) -> dict[str, object]:
    """다음 질문 번호와 이미 확정된 답변 수를 혼동하지 않도록 코드에서 계산한다."""
    answered = len(context.history)
    if context.turn_no != answered + 1:
        raise c.ContractError("semantic", "next question turn")
    if context.current_turn_id != (context.history[-1].turn_id if answered else None):
        raise c.ContractError("semantic", "last answered turn")
    observed = {turn.persona for turn in context.history}
    counts = {item.persona: item.count for item in context.persona_counts}
    if any(
        counts.get(persona, 0) != sum(turn.persona == persona for turn in context.history)
        for persona in observed | counts.keys()
    ):
        raise c.ContractError("semantic", "answered persona counts")
    return {
        "phase": "generate_next_question",
        "next_question_no": context.turn_no,
        "answered_turn_count": answered,
        "last_answered_turn_no": answered or None,
        "last_answered_turn_id": context.current_turn_id,
        "total_questions": context.total_turns,
        "remaining_questions": context.total_turns - answered,
        "is_final_question": context.turn_no == context.total_turns,
        "finish_authority": "controller_after_final_answer",
    }


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
    if prompt.version.partition("@")[0] not in SUPPORTED_PROMPT_VERSIONS:
        raise c.ContractError("schema", "unsupported Director prompt version")
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
    current_answer = None
    if context.current_turn_id is not None:
        # 직전 발언을 분석 요약·다른 턴과 섞지 않고 두 모델 시도에 같은 원문으로 제공한다.
        current = tuple(turn for turn in context.history if turn.turn_id == context.current_turn_id)
        if len(current) != 1 or context.current_question_contract is None:
            raise c.ContractError("semantic", "current answered turn")
        current_answer = {
            "turn_id": current[0].turn_id,
            "question": current[0].question,
            "answer": current[0].answer,
            "question_contract": asdict(context.current_question_contract),
        }
    payload: dict[str, object] = {
        "context": asdict(context),
        "current_answer": current_answer,
        "reference_texts": _model_reference_texts(sources),
        "answer_analysis": analysis,
        "prior_analyses": previous,
        "tool_results": [asdict(result) for result in tool_results],
    }
    if prompt.version.partition("@")[0] in {
        "director_v5",
        "director_v6",
        "director_v7",
        "director_v8",
    }:
        # 기존 버전의 입력을 바꾸지 않고 새 배포에만 명시적인 턴 의미를 제공한다.
        payload["turn_state"] = _turn_state(context)
    return payload, sources


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
    recovery_feedback: RecoveryFeedback | None = None,
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
        # 과거 프롬프트에는 복구 참고자료의 취급 지침이 없으므로 입력을 소급 확장하지 않는다.
        feedback = (
            _feedback_payload(recovery_feedback)
            if recovery_feedback is not None
            and prompt.version.partition("@")[0] in {"director_v7", "director_v8"}
            else None
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

    # 구형 출력 계약만 보존하고 새 버전·배포 suffix에서는 평가 기회 검증을 유지한다.
    legacy = prompt.version.partition("@")[0] in {"director_v1", "director_v2"}
    coverage = bool(context.evaluation_targets) and not legacy
    bounded_ids = prompt.version.partition("@")[0] in {"director_v6", "director_v7", "director_v8"}

    def validate_plan(raw: object) -> _Plan:
        if type(raw) is not dict or set(raw) != {"question", "intent", "reason_summary"}:
            raise c.ContractError("schema", "DirectorPlan")
        candidate = _validate_candidate(_plan_question(raw["question"]), context, sources, coverage)
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
            {
                **payload,
                "operation": "plan",
                **({"recovery_feedback": feedback} if feedback is not None else {}),
            },
            "DirectorPlan",
            "director-plan.v3"
            if bounded_ids
            else "director-plan.v2"
            if coverage
            else "director-plan.v1",
            _bounded_plan_schema(context, sources, coverage)
            if bounded_ids
            else _plan_schema(coverage),
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
        _validate_candidate(plan.question, context, sources, coverage)
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


def external_verification_queries(
    context: c.Context, analysis: c.ContractChecked[c.AnswerAnalysis]
) -> tuple[c.ExternalQueryRequest, ...]:
    """검증된 현재 답변의 보완 요청만 외부 Tool 후보로 넘긴다. 검색 실행은 BE 책임이다."""
    if type(context) is not c.Context or context.current_turn_id is None:
        raise c.ContractError("semantic", "external query turn")
    if type(analysis) is not c.ContractChecked or type(analysis.data) is not c.AnswerAnalysis:
        raise c.ContractError("schema", "checked analysis")
    return analysis.data.external_queries if analysis.data.needs_verification else ()


def verification_decision(
    context: c.Context,
    analysis: c.ContractChecked[c.AnswerAnalysis],
    *,
    allowed_locations: frozenset[Location],
) -> c.ContractChecked[c.DirectorDecision] | str:
    """현재 T3의 명시적 필요·영향 판단에서 허용된 추가 조회만 제안한다.

    기존 근거가 충분하다고 분석한 주장은 제외한다. 원문 의미의 충분성과 현재
    판단에 대한 영향은 검증된 T3의 요청·목적에 의존한다. 조회·감점·종료는 하지 않는다.
    수집한 경로만 다시 읽는 요청은 새 경로 요청 뒤로, 같은 단계는 좁은 범위 먼저 정렬하며
    BE는 앞에서부터 실행한다.
    조회하지 않으면 미조회 사유 문자열을 반환하며 BE는 이를 정상 조회 후 미발견과 구분해
    기존 reason_summary에 남긴다(0014). 허용 범위 밖 요청은 사유로 바꾸지 않고 거절한다.
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
        # 필요성·영향·허용 범위 중 미충족 조건을 계약에 없는 정보로 단정하지 않는다.
        return "추가 조회 조건을 충족하지 않아 조회하지 않음"
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
        return "요청한 주장이 모두 등록 근거로 지지됨"
    collected = {
        (item.repository_id, item.git_ref, item.path)
        for item in context.evidence
        if item.path is not None
    }
    # 수집한 경로만 다시 읽는 요청은 빼지 않고 새 경로 요청 뒤에 둔다. Evidence 계약은 부분 줄
    # 범위를 허용하고 파일 전체 확보 여부를 표시하지 않아, 경로만으로 재조회가 불필요하다고 볼 수
    # 없다. 전체 원문 표시가 계약에 생기면 그 근거만 있는 요청은 제외한다(0003 조건 1).
    # 같은 단계는 확인 범위가 좁은 요청을 먼저 두고, 그 외에는 모델 순서를 유지한다(stable sort).
    # 인접 후보(AI-L08, BE 미공급)와 주장 종류별 source 적합성(요청에 종류 필드 없음)은
    # 반영하지 않는다. 두 입력이 계약에 생기면 정렬 키에 단계를 추가한다.
    requests = tuple(
        sorted(
            requests,
            key=lambda request: (
                all(
                    (request.repository_id, request.git_ref, path) in collected
                    for path in request.allowed_paths
                ),
                len(request.allowed_paths),
            ),
        )
    )
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
