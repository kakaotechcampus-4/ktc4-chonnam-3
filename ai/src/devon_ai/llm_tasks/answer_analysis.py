"""One qualitative analysis; persistence, tools and next-turn decisions belong to BE."""

import json
from dataclasses import asdict, replace

from devon_ai import contracts as c
from devon_ai.llm_tasks import ModelCall, call_model


def _question_payload(question: c.Question) -> dict[str, object]:
    return {"text": question.text, "question_contract": asdict(question.question_contract)}


def _history_payload(history: tuple[c.AnalysisHistory, ...], turn: int) -> list[dict[str, object]]:
    if type(history) is not tuple or any(type(item) is not c.AnalysisHistory for item in history):
        raise c.ContractError("schema", "analysis history")
    turns = [item.answer.turn for item in history]
    if turns != sorted(set(turns)) or any(previous >= turn for previous in turns):
        raise c.ContractError("semantic", "history turn order")
    return [
        {
            "question": _question_payload(item.question.data),
            "answer": asdict(item.answer),
            "analysis": asdict(item.analysis.data),
        }
        for item in history
    ]


def _current_evidence(
    evidence: tuple[c.AnalysisEvidence, ...],
    tool_results: tuple[c.AnalysisToolResult, ...],
    evidence_refs: frozenset[str],
    allowed_locations: frozenset[tuple[str, str, str]],
) -> tuple[c.AnalysisEvidence, ...]:
    c._convert(tuple[c.AnalysisEvidence, ...], evidence, "evidence", wire=False)
    c._convert(tuple[c.AnalysisToolResult, ...], tool_results, "tool results", wire=False)
    c._requests((), allowed_locations)
    registry: dict[str, c.AnalysisEvidence] = {}
    for item in (*evidence, *(item for result in tool_results for item in result.items)):
        if (item.repository_id, item.git_ref, item.path) not in allowed_locations:
            raise c.ContractError("semantic", "evidence location")
        if item.evidence_id in registry and registry[item.evidence_id] != item:
            raise c.ContractError("semantic", "conflicting evidence identity")
        registry[item.evidence_id] = item
    c._references((), evidence_refs, "evidence registry")
    c._references(tuple(evidence_refs), frozenset(registry), "missing evidence content")
    return tuple(item for key, item in registry.items() if key in evidence_refs)


async def analyze_answer(
    request: c.ModelRequest,
    *,
    question: c.ContractChecked[c.Question],
    question_turn: int,
    answer: c.SubmittedAnswer,
    client: ModelCall,
    evidence: tuple[c.AnalysisEvidence, ...] = (),
    tool_results: tuple[c.AnalysisToolResult, ...] = (),
    evidence_refs: frozenset[str] = frozenset(),
    allowed_locations: frozenset[tuple[str, str, str]] = frozenset(),
    history: tuple[c.AnalysisHistory, ...] = (),
) -> c.ModelSuccess[c.AnswerAnalysis] | c.ModelFailed:
    """Use BE's common rubric/config and build input from confirmed task arguments.

    request.input_json is replaced, never merged with unchecked caller content.
    BE supplies only persisted submissions and checks user/session ownership.
    Natural-language judgement belongs to the injected model; local checks bind
    its three independent axes to the question, quotes and permitted evidence.
    """
    value = c._checked_data(question, c.Question)
    if type(answer) is not c.SubmittedAnswer:
        raise c.ContractError("schema", "submitted answer")
    if type(question_turn) is not int or question_turn != answer.turn:
        raise c.ContractError("semantic", "answer turn mismatch")
    if request.task_name != "answer_analysis_v1":
        raise c.ContractError("schema", "analysis task")
    selected = _current_evidence(evidence, tool_results, evidence_refs, allowed_locations)
    payload = {
        "question_turn": question_turn,
        "question": _question_payload(value),
        "answer": asdict(answer),
        "history": _history_payload(history, question_turn),
        "evidence": [asdict(item) for item in selected],
        "tool_results": [asdict(result) for result in tool_results],
        "allowed_locations": sorted(allowed_locations),
    }

    def validate(candidate: c.AnswerAnalysis) -> c.ContractChecked[c.AnswerAnalysis]:
        return c.validate_analysis(
            candidate,
            question=question,
            answer_text=answer.text,
            evidence_refs=evidence_refs,
            allowed_locations=allowed_locations,
        )

    return await call_model(
        replace(request, input_json=json.dumps(payload, ensure_ascii=False)),
        client=client,
        contract_type=c.AnswerAnalysis,
        validate=validate,
    )
