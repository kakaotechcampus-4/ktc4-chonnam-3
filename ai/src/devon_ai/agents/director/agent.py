"""준비된 목적의 질문 하나를 생성한다. 면접 준비·상태 확정·발행은 BE 책임이다."""

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import asdict

from devon_ai import contracts as c

type QuestionReviewer = Callable[[c.ModelRequest, c.Question], Awaitable[c.QuestionReview]]


def _object_schema(properties: dict[str, object]) -> dict[str, object]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def _question_schema() -> dict[str, object]:
    # 모델에는 구조를 제한하고, 원문·참조·계획의 일치는 아래 validator에서 별도로 확인한다.
    text = {"type": "string"}
    texts = {"type": "array", "items": text}
    contract = _object_schema(
        {
            "purpose": text,
            "required_points": {
                "type": "array",
                "items": _object_schema(
                    {
                        "key": text,
                        "description": text,
                    }
                ),
            },
            "assumptions": texts,
            "basis_refs": {
                "type": "array",
                "items": _object_schema(
                    {
                        "kind": {
                            "type": "string",
                            "enum": ["evidence", "jd_requirement", "job_posting", "answer_turn"],
                        },
                        "id": text,
                    }
                ),
            },
            "evaluation_scope": text,
        }
    )
    return _object_schema(
        {
            "persona": {"type": "string", "enum": ["hr_manager", "tech_lead", "domain_lead"]},
            "text": text,
            "topic_code": text,
            "question_contract": contract,
            "evidence_refs": texts,
            "jd_requirement_ids": texts,
        }
    )


def _references(
    context: c.Context,
    extra: Mapping[c.BasisRef, str],
) -> dict[c.BasisRef, str]:
    """주입된 원문에서 참조를 구성하며 모델이 만든 ID를 유효한 근거로 등록하지 않는다."""
    sources: dict[c.BasisRef, str] = {}
    repositories = {repo.repository_id: repo.git_ref for repo in context.repositories}
    if len(repositories) != len(context.repositories):
        raise c.ContractError("semantic", "duplicate repository")

    def add(ref: c.BasisRef, text: str) -> None:
        if ref in sources:
            raise c.ContractError("semantic", "duplicate source")
        sources[ref] = text

    for item in context.evidence:
        if item.repository_id is not None and repositories.get(item.repository_id) != item.git_ref:
            raise c.ContractError("semantic", "evidence repository ref")
        if item.evidence_id is not None:
            add(c.BasisRef("evidence", item.evidence_id), item.content)
    for requirement in context.jd_requirements:
        add(c.BasisRef("jd_requirement", requirement.id), requirement.text)
    for turn in context.history:
        add(c.BasisRef("answer_turn", turn.turn_id), turn.answer)
    for ref, text in extra.items():
        if type(ref) is not c.BasisRef or type(text) is not str or not text.strip():
            raise c.ContractError("schema", "source text")
        if ref in sources:
            if sources[ref] != text:
                raise c.ContractError("semantic", "conflicting source text")
        elif ref.kind == "job_posting":
            # Context에 없는 공고 ID·본문은 BE가 권한을 확인해 명시적으로 제공해야 한다.
            add(ref, text)
        else:
            raise c.ContractError("semantic", "source outside context")
    return sources


async def generate_question(
    context: c.Context,
    question_contract: c.QuestionContract,
    *,
    prompt: c.PromptSpec,
    limits: c.CallLimits,
    model_call: c.ModelCall[c.Question],
    review: QuestionReviewer,
    answer_analysis: c.ContractChecked[c.AnswerAnalysis] | None = None,
    reference_texts: Mapping[c.BasisRef, str] | None = None,
) -> c.ModelResult[c.ContractChecked[c.Question]]:
    """후보 하나를 생성·독립 검토하며 재시도와 면접 상태 변경을 직접 수행하지 않는다.

    이 함수의 context.turn_no는 생성할 질문 번호다. BE가 준비 상태·허용 Persona와
    현재 문답에 대응하는 이력·분석을 확인해 전달한다. 검토기는 정확한 후보와 전체
    입력 원문을 받아 의미 검토 후 QuestionReview를 반환하거나 ContractError로 거절한다.
    검토 시간은 limits.timeout_seconds로 제한하고 모델 시도의 시간·횟수는 공통 호출
    계층에서 제한한다. 취소와 예상하지 못한 프로그래밍 오류는 상위 호출자에게 전파한다.
    """
    # 패키지 import만으로 플랫폼별 비동기 실행 환경을 초기화하지 않도록 늦게 불러온다.
    import asyncio

    try:
        if type(context) is not c.Context or type(question_contract) is not c.QuestionContract:
            raise c.ContractError("schema", "Director input")
        if type(prompt) is not c.PromptSpec or prompt.task_name != "director":
            raise c.ContractError("schema", "Director prompt")
        if type(limits) is not c.CallLimits:
            raise c.ContractError("schema", "Director limits")
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
        analysis_data = None
        if answer_analysis is not None:
            if (
                type(answer_analysis) is not c.ContractChecked
                or type(answer_analysis.data) is not c.AnswerAnalysis
            ):
                raise c.ContractError("schema", "checked answer analysis")
            analysis_data = c.to_data(answer_analysis)
        if reference_texts is not None and not isinstance(reference_texts, Mapping):
            raise c.ContractError("schema", "source text mapping")
        sources = _references(context, {} if reference_texts is None else reference_texts)
        if not set(question_contract.basis_refs).issubset(sources):
            raise c.ContractError("semantic", "planned source missing")
    except c.ContractError as exc:
        return c.ModelResult(
            None, c.CallFailure(exc.stage, "director_input_invalid", "Director input rejected."), ()
        )
    if context.limits.remaining_calls == 0:
        return c.ModelResult(
            None, c.CallFailure("budget", "llm_failed", "No provider attempts remain."), ()
        )

    evidence_refs = frozenset(ref.id for ref in sources if ref.kind == "evidence")
    jd_ids = frozenset(ref.id for ref in sources if ref.kind == "jd_requirement")
    basis_refs = frozenset(sources)

    def validate_candidate(candidate: c.Question) -> c.Question:
        # 표현을 생성하는 단계에서 이미 정한 목적·확인내용·근거를 다른 계획으로 바꿀 수 없다.
        if candidate.question_contract != question_contract:
            raise c.ContractError("semantic", "prepared question contract")
        return c.validate_question_candidate(
            candidate,
            allowed_personas=context.allowed_personas,
            evidence_refs=evidence_refs,
            basis_refs=basis_refs,
            jd_requirement_ids=jd_ids,
        )

    def validate(raw: object) -> c.Question:
        return validate_candidate(c.decode(c.Question, raw))

    request = c.ModelRequest(
        prompt=prompt,
        payload={
            "context": asdict(context),
            "question_contract": asdict(question_contract),
            "reference_texts": [
                {"kind": ref.kind, "id": ref.id, "text": text} for ref, text in sources.items()
            ],
            "answer_analysis": analysis_data,
        },
        schema_name="DirectorQuestion",
        schema_version="1",
        output_schema=_question_schema(),
        limits=limits,
        max_attempts=min(2, context.limits.remaining_calls),
    )
    result = await model_call(request, validate)
    if result.failure is not None:
        return c.ModelResult(None, result.failure, result.attempts)
    # 주입된 callable이 validator를 생략했더라도 검토 전에 동일한 정책을 다시 확인한다.
    candidate = result.data
    if type(candidate) is not c.Question:
        raise TypeError("ModelCall did not return a validated Question candidate")
    try:
        validate_candidate(candidate)
    except c.ContractError as exc:
        return c.ModelResult(
            None,
            c.CallFailure(exc.stage, "director_candidate_invalid", "Question candidate rejected."),
            result.attempts,
        )
    try:
        async with asyncio.timeout(limits.timeout_seconds):
            assessment = await review(request, candidate)
        # 생성 모델의 자기평가 대신 같은 문장·계약에 대한 독립 검토 결과를 요구한다.
        checked = c.validate_question(
            candidate,
            review=assessment,
            allowed_personas=context.allowed_personas,
            evidence_refs=evidence_refs,
            basis_refs=basis_refs,
            jd_requirement_ids=jd_ids,
        )
    except c.ContractError:
        # 검토기의 형식 오류도 생성 모델 재시도 사유가 아니다. 기존 호출 기록은 그대로 둔다.
        return c.ModelResult(
            None,
            c.CallFailure(
                "semantic", "director_review_failed", "Independent question review rejected."
            ),
            result.attempts,
        )
    except TimeoutError:
        return c.ModelResult(
            None,
            c.CallFailure(
                "timeout", "director_review_timeout", "Independent question review timed out."
            ),
            result.attempts,
        )
    return c.ModelResult(checked, None, result.attempts)
