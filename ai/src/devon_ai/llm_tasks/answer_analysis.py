"""One qualitative analysis; persistence, tools and next-turn decisions belong to BE."""

import json
from dataclasses import asdict, replace

from devon_ai import contracts as c
from devon_ai.llm_tasks import ModelCall, call_model


async def analyze_answer(
    request: c.ModelRequest,
    *,
    question: c.ContractChecked[c.Question],
    question_turn: int,
    answer: c.SubmittedAnswer,
    client: ModelCall,
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
    payload = {
        "question_turn": question_turn,
        "question": {
            "text": value.text,
            "question_contract": asdict(value.question_contract),
        },
        "answer": asdict(answer),
    }

    def validate(candidate: c.AnswerAnalysis) -> c.ContractChecked[c.AnswerAnalysis]:
        return c.validate_analysis(
            candidate,
            question=question,
            answer_text=answer.text,
            evidence_refs=frozenset(),
            allowed_locations=frozenset(),
        )

    return await call_model(
        replace(request, input_json=json.dumps(payload, ensure_ascii=False)),
        client=client,
        contract_type=c.AnswerAnalysis,
        validate=validate,
    )
