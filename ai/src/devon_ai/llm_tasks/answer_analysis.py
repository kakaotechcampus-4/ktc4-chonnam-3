"""제출된 답변의 정성 분석 후보를 만든다. prompt 로드·provider I/O·저장·Tool 실행은 BE 책임이다."""

from dataclasses import asdict, fields

from devon_ai import contracts as c

type AnalysisChecked = c.ContractChecked[c.AnswerAnalysis]
type Location = tuple[str, str, str]


def _object(properties: dict[str, object]) -> dict[str, object]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def _output_schema() -> dict[str, object]:
    text = {"type": "string"}
    texts = {"type": "array", "items": text}
    covered = _object({"key": text, "answer_quotes": texts})
    technical = _object(
        {"explanation": text, "answer_quotes": texts, "evidence_refs": texts, "limitations": texts}
    )
    contribution = _object(
        {"scope": {"enum": ["self", "shared", "teammate", "unknown"]}, "answer_quotes": texts}
    )
    claim = _object(
        {
            "claim_text": text,
            "status": {"enum": ["supported", "partially_supported", "unverified", "conflicting"]},
            "evidence_refs": texts,
            "limitations": texts,
        }
    )
    verification = _object(
        {
            "claim_text": text,
            "purpose": text,
            "repository_id": text,
            "git_ref": text,
            "allowed_paths": texts,
        }
    )
    return _object(
        {
            "evaluation_status": {"enum": ["evaluated", "needs_clarification", "not_evaluable"]},
            "sufficiency": {"enum": ["sufficient", "partial", "insufficient", None]},
            "covered_points": {"type": "array", "items": covered},
            "missing_points": texts,
            "technical_assessment": technical,
            "contribution_scope": contribution,
            "claim_checks": {"type": "array", "items": claim},
            "needs_verification": {"type": "boolean"},
            "verification_requests": {"type": "array", "items": verification},
            "limitations": texts,
        }
    )


def _evidence_ids(context: c.Context, tool_results: tuple[c.ToolResult, ...]) -> frozenset[str]:
    """주입된 자료의 등록 ID만 근거로 인정하며 모델이 만든 ID는 등록하지 않는다."""
    refs = {repo.repository_id: repo.git_ref for repo in context.repositories}
    if len(refs) != len(context.repositories):
        raise c.ContractError("semantic", "duplicate repository")
    ids: list[str] = []
    items = context.evidence + tuple(item for result in tool_results for item in result.items)
    for item in items:
        if item.repository_id is not None and refs.get(item.repository_id) != item.git_ref:
            raise c.ContractError("semantic", "evidence repository ref")
        if item.evidence_id is not None:
            ids.append(item.evidence_id)
    if len(set(ids)) != len(ids):
        raise c.ContractError("semantic", "duplicate evidence")
    return frozenset(ids)


def _check_input(
    context: c.Context,
    question: c.ContractChecked[c.Question],
    turn_id: str,
    answer_text: str,
    tool_results: tuple[c.ToolResult, ...],
    allowed_locations: frozenset[Location],
) -> frozenset[str]:
    """질문·Contract·제출 답변의 대응을 모델을 부르기 전에 코드로 확인한다."""
    if type(context) is not c.Context:
        raise c.ContractError("schema", "context")
    if type(question) is not c.ContractChecked or type(question.data) is not c.Question:
        raise c.ContractError("schema", "checked question")
    if type(turn_id) is not str or not turn_id.strip():
        raise c.ContractError("schema", "turn_id")
    # 빈 값은 제출된 답변이 아닌 초안·전송 오류로 보며 "모르겠습니다"는 정상 답변이다.
    if type(answer_text) is not str or not answer_text.strip():
        raise c.ContractError("semantic", "submitted answer")
    if type(tool_results) is not tuple or any(type(r) is not c.ToolResult for r in tool_results):
        raise c.ContractError("schema", "tool_results")
    if context.current_turn_id != turn_id:
        raise c.ContractError("semantic", "answer turn")
    if any(turn.turn_id == turn_id for turn in context.history):
        raise c.ContractError("semantic", "answer already in history")
    if context.current_question_contract != question.data.question_contract:
        raise c.ContractError("semantic", "question contract")
    if type(allowed_locations) is not frozenset:
        raise c.ContractError("schema", "allowed_locations")
    refs = {repo.repository_id: repo.git_ref for repo in context.repositories}
    for location in allowed_locations:
        if (
            type(location) is not tuple
            or len(location) != 3
            or refs.get(location[0]) != location[1]
        ):
            raise c.ContractError("semantic", "allowed location ref")
    return _evidence_ids(context, tool_results)


def _payload(
    context: c.Context,
    question: c.Question,
    turn_id: str,
    answer_text: str,
    tool_results: tuple[c.ToolResult, ...],
    allowed_locations: frozenset[Location],
) -> dict[str, object]:
    # 평가 기준은 Persona에 따라 달라지지 않으므로 질문·이력에서 Persona를 빼고 전달한다.
    return {
        "question": {
            "text": question.text,
            "topic_code": question.topic_code,
            "question_contract": asdict(question.question_contract),
        },
        "answer": {"turn_id": turn_id, "text": answer_text},
        "history": [
            {
                "turn_id": turn.turn_id,
                "question": turn.question,
                "answer": turn.answer,
                "analysis_ref": turn.analysis_ref,
            }
            for turn in context.history
        ],
        "evidence": [asdict(item) for item in context.evidence],
        "tool_results": [asdict(result) for result in tool_results],
        "allowed_locations": sorted(list(item) for item in allowed_locations),
    }


async def analyze_answer(
    context: c.Context,
    question: c.ContractChecked[c.Question],
    *,
    turn_id: str,
    answer_text: str,
    prompt: c.PromptSpec,
    limits: c.CallLimits,
    model_call: c.ModelCall[AnalysisChecked],
    tool_results: tuple[c.ToolResult, ...] = (),
    allowed_locations: frozenset[Location] = frozenset(),
) -> c.ModelResult[AnalysisChecked]:
    """제출된 답변 하나의 분석 후보를 만들고 validate_analysis를 통과한 값만 반환한다.

    context.current_turn_id·current_question_contract가 turn_id·question과 맞아야 하며 답변은
    아직 history에 없어야 한다. 재시도와 Tool 실행은 하지 않는다. 모델 시도의 횟수·시간은
    공통 호출 계층이 제한하고 semantic 실패는 재호출하지 않는다. tool_results와
    allowed_locations는 BE가 권한을 확인해 전달하며 조회 후보의 범위를 이 안으로 제한한다.
    """
    try:
        if type(prompt) is not c.PromptSpec or prompt.task_name != "answer_analysis":
            raise c.ContractError("schema", "answer_analysis prompt")
        if type(limits) is not c.CallLimits:
            raise c.ContractError("schema", "answer_analysis limits")
        evidence_refs = _check_input(
            context, question, turn_id, answer_text, tool_results, allowed_locations
        )
    except c.ContractError as exc:
        failure = c.CallFailure(
            exc.stage, "answer_analysis_input_invalid", "Analysis input rejected."
        )
        return c.ModelResult(None, failure, ())
    if context.limits.remaining_calls == 0:
        return c.ModelResult(
            None, c.CallFailure("budget", "llm_failed", "No provider attempts remain."), ()
        )

    def validate_checked(candidate: c.AnswerAnalysis) -> AnalysisChecked:
        return c.validate_analysis(
            candidate,
            question=question,
            answer_text=answer_text,
            evidence_refs=evidence_refs,
            allowed_locations=allowed_locations,
        )

    def validate(raw: object) -> AnalysisChecked:
        # 계약 밖의 최상위 필드(점수 등)를 조용히 버리지 않고 schema 실패로 처리한다.
        if type(raw) is not dict or set(raw) != {item.name for item in fields(c.AnswerAnalysis)}:
            raise c.ContractError("schema", "AnswerAnalysis")
        return validate_checked(c.decode(c.AnswerAnalysis, raw))

    request = c.ModelRequest(
        prompt=prompt,
        payload=_payload(
            context, question.data, turn_id, answer_text, tool_results, allowed_locations
        ),
        schema_name="AnswerAnalysis",
        schema_version="1",
        output_schema=_output_schema(),
        limits=limits,
        max_attempts=min(2, context.limits.remaining_calls),
    )
    result = await model_call(request, validate)
    if result.data is None:
        return result
    # 주입된 callable이 validator를 생략했더라도 이 질문·답변 기준으로 다시 확인한다.
    checked = result.data
    if type(checked) is not c.ContractChecked or type(checked.data) is not c.AnswerAnalysis:
        raise TypeError("ModelCall did not return a checked AnswerAnalysis")
    try:
        validate_checked(checked.data)
    except c.ContractError as exc:
        failure = c.CallFailure(
            exc.stage, "answer_analysis_invalid", "Analysis candidate rejected."
        )
        return c.ModelResult(None, failure, result.attempts)
    return result
