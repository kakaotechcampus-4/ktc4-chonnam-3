"""제출된 답변의 정성 분석 후보를 만든다. prompt 로드·provider I/O·저장·Tool 실행은 BE 책임이다."""

from dataclasses import MISSING, asdict, fields

from devon_ai import contracts as c
from devon_ai.llm_tasks import answer_analysis_wire as wire

SUPPORTED_PROMPT_VERSIONS = frozenset(
    {
        "answer_analysis_v1",
        "answer_analysis_v5",
        "answer_analysis_v2",
        "answer_analysis_v4",
        "answer_analysis_v3",
        "answer_analysis_v6",
    }
)


type AnalysisChecked = c.ContractChecked[c.AnswerAnalysis]
type Location = tuple[str, str, str]


def _object(properties: dict[str, object]) -> dict[str, object]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def _output_schema(
    *, evidence_refs: frozenset[str], include_external: bool = False, strict_claims: bool = False
) -> dict[str, object]:
    text = {"type": "string"}
    texts = {"type": "array", "items": text}
    # 문서 주장·시각 해석의 source_id는 등록된 코드 Evidence ID와 별개다.
    references: dict[str, object] = {"type": "array", "items": {"type": "string"}}
    if evidence_refs:
        references["items"] = {"type": "string", "enum": sorted(evidence_refs)}
    else:
        references["maxItems"] = 0
    covered = _object({"key": text, "answer_quotes": texts})
    technical = _object(
        {
            "explanation": text,
            "answer_quotes": texts,
            "evidence_refs": references,
            "limitations": texts,
        }
    )
    contribution = _object(
        {"scope": {"enum": ["self", "shared", "teammate", "unknown"]}, "answer_quotes": texts}
    )
    claim = _object(
        {
            "claim_text": text,
            "status": {"enum": ["supported", "partially_supported", "unverified", "conflicting"]},
            "evidence_refs": references,
            "limitations": texts,
        }
    )
    if strict_claims:
        # 사실 판정과 미확인 주장의 조건을 생성 단계에도 전달한다. 의미 검증은 유지한다.
        variants = [
            _object(
                {
                    "claim_text": text,
                    "status": {"enum": ["unverified"]},
                    "evidence_refs": references,
                    "limitations": {**texts, "minItems": 1},
                }
            )
        ]
        if evidence_refs:
            variants.append(
                _object(
                    {
                        "claim_text": text,
                        "status": {"enum": ["supported", "partially_supported", "conflicting"]},
                        "evidence_refs": {**references, "minItems": 1},
                        "limitations": texts,
                    }
                )
            )
        claim = {"anyOf": variants}
    verification = _object(
        {
            "claim_text": text,
            "purpose": text,
            "repository_id": text,
            "git_ref": text,
            "allowed_paths": texts,
        }
    )
    result = _object(
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
            "external_queries": {
                "type": "array",
                "items": _object({"query": text, "purpose": text}),
            },
        }
    )
    if not include_external:
        properties = result["properties"]
        assert isinstance(properties, dict)
        properties.pop("external_queries")
        result["required"] = list(properties)
    return result


def _evidence_ids(context: c.Context, tool_results: tuple[c.ToolResult, ...]) -> frozenset[str]:
    """주입된 자료의 등록 ID만 근거로 인정하며 모델이 만든 ID는 등록하지 않는다."""
    refs = {repo.repository_id: repo.git_ref for repo in context.repositories}
    if len(refs) != len(context.repositories):
        raise c.ContractError("semantic", "duplicate repository")
    registered: dict[str, c.Evidence] = {}
    for item in context.evidence:
        if item.evidence_id is not None:
            if item.evidence_id in registered:
                raise c.ContractError("semantic", "duplicate evidence")
            registered[item.evidence_id] = item
    for item in context.evidence + tuple(item for result in tool_results for item in result.items):
        if item.repository_id is not None and refs.get(item.repository_id) != item.git_ref:
            raise c.ContractError("semantic", "evidence repository ref")
        if item.evidence_id is not None:
            # 기존 원문을 다시 조회하면 저장된 ID를 재사용할 수 있다.
            previous = registered.get(item.evidence_id)
            if previous is not None and previous != item:
                raise c.ContractError("semantic", "conflicting evidence ID")
            registered[item.evidence_id] = item
    return frozenset(registered)


def _referenced_jd(context: c.Context, question: c.Question) -> tuple[c.JDRequirement, ...]:
    """질문의 두 참조 경로가 요구하는 JD 원문만 모으며 누락·중복 ID는 거절한다."""
    registered = {item.id: item for item in context.jd_requirements}
    if len(registered) != len(context.jd_requirements):
        raise c.ContractError("semantic", "duplicate JD requirement")
    ids = tuple(
        dict.fromkeys(
            question.jd_requirement_ids
            + tuple(
                ref.id
                for ref in question.question_contract.basis_refs
                if ref.kind == "jd_requirement"
            )
        )
    )
    if any(identifier not in registered for identifier in ids):
        raise c.ContractError("semantic", "missing JD requirement")
    return tuple(registered[identifier] for identifier in ids)


def _check_input(
    context: c.Context,
    question: c.ContractChecked[c.Question],
    turn_id: str,
    answer_text: str,
    tool_results: tuple[c.ToolResult, ...],
    allowed_locations: frozenset[Location],
) -> tuple[frozenset[str], tuple[c.JDRequirement, ...]]:
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
    return _evidence_ids(context, tool_results), _referenced_jd(context, question.data)


def _payload(
    context: c.Context,
    question: c.Question,
    turn_id: str,
    answer_text: str,
    tool_results: tuple[c.ToolResult, ...],
    allowed_locations: frozenset[Location],
    jd_requirements: tuple[c.JDRequirement, ...],
    evidence_refs: frozenset[str],
) -> dict[str, object]:
    # 평가 기준은 Persona에 따라 달라지지 않으므로 질문·이력에서 Persona를 빼고 전달한다.
    return {
        "question": {
            "text": question.text,
            "topic_code": question.topic_code,
            "question_contract": asdict(question.question_contract),
            "jd_requirement_ids": list(question.jd_requirement_ids),
        },
        "jd_requirements": [asdict(item) for item in jd_requirements],
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
        "allowed_evidence_refs": sorted(evidence_refs),
        "supplemental_sources": [asdict(item) for item in context.supplemental_sources],
        "external_searches": [asdict(item) for item in context.external_searches],
        "supplemental_limitations": list(context.supplemental_limitations),
        "tool_results": [asdict(result) for result in tool_results],
        "allowed_locations": sorted(list(item) for item in allowed_locations),
    }


def decode_analysis_output(
    raw: object,
    *,
    prompt_version: str | None,
    answer_text: str,
    contract: c.QuestionContract,
    schema_version: str | None = None,
) -> c.AnswerAnalysis:
    """감사 원문은 보존하고 해당 버전의 표현으로만 과거 분석을 복원한다."""
    if prompt_version is not None and prompt_version.partition("@")[0] == "answer_analysis_v6":
        if schema_version != "6":
            raise c.ContractError("semantic", "analysis wire version")
        raw_wire = raw
        raw = wire.canonical_output(
            raw, answer=answer_text, keys=tuple(point.key for point in contract.required_points)
        )
        wire.validate_wire_constraints(raw_wire)
    return c.decode_strict(c.AnswerAnalysis, raw)


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
        evidence_refs, jd_requirements = _check_input(
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
        # 새 모델 출력만 실행 정책으로 확인한다. 과거 저장 분석의 decode는 바꾸지 않는다.
        for query in candidate.external_queries:
            query.validate_for_execution()
        return c.validate_analysis(
            candidate,
            question=question,
            answer_text=answer_text,
            evidence_refs=evidence_refs,
            allowed_locations=allowed_locations,
        )

    base_version = prompt.version.partition("@")[0]
    include_external = base_version != "answer_analysis_v1"
    keys = tuple(point.key for point in question.data.question_contract.required_points)
    units = wire.answer_units(answer_text) if base_version == "answer_analysis_v6" else ()
    if base_version == "answer_analysis_v6" and (not keys or not units):
        return c.ModelResult(
            None,
            c.CallFailure("semantic", "answer_analysis_input_invalid", "Analysis input rejected."),
            (),
        )

    def validate(raw: object) -> AnalysisChecked:
        if base_version == "answer_analysis_v6":
            return validate_checked(
                decode_analysis_output(
                    raw,
                    prompt_version=prompt.version,
                    answer_text=answer_text,
                    contract=question.data.question_contract,
                    schema_version="6",
                )
            )
        # 계약 밖의 최상위 필드(점수 등)를 조용히 버리지 않고 schema 실패로 처리한다.
        declared = fields(c.AnswerAnalysis)
        names = {item.name for item in declared}
        required = {
            item.name
            for item in declared
            if item.default is MISSING and item.default_factory is MISSING
        }
        # 과거 저장 결과에 없던 선택 필드만 기본값으로 읽고 필수 필드·추가 필드 검사는 유지한다.
        if type(raw) is not dict or not required <= set(raw) or not set(raw) <= names:
            raise c.ContractError("schema", "AnswerAnalysis")
        if not include_external and raw.get("external_queries"):
            raise c.ContractError("schema", "external query policy")
        return validate_checked(c.decode(c.AnswerAnalysis, raw))

    payload = _payload(
        context,
        question.data,
        turn_id,
        answer_text,
        tool_results,
        allowed_locations,
        jd_requirements,
        evidence_refs,
    )
    if base_version == "answer_analysis_v6":
        payload["answer_units"] = wire.units_payload(units)
    request = c.ModelRequest(
        prompt=prompt,
        payload=payload,
        schema_name="AnswerAnalysis",
        schema_version={
            "answer_analysis_v3": "3",
            "answer_analysis_v4": "4",
            "answer_analysis_v5": "5",
            "answer_analysis_v6": "6",
        }.get(base_version, "2" if include_external else "1"),
        output_schema=wire.output_schema(keys, units, evidence_refs, allowed_locations)
        if base_version == "answer_analysis_v6"
        else _output_schema(
            evidence_refs=evidence_refs,
            include_external=include_external,
            strict_claims=base_version == "answer_analysis_v5",
        ),
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
