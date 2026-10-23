"""목적·질문을 함께 제안하고 별도 모델 시도로 검토하는 단일 Director 실행 경로."""

from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
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
