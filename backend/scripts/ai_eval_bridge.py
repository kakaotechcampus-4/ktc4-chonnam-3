"""로컬 평가 입력을 실제 서비스 AI 계약과 실행 함수에 연결한다."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from dataclasses import asdict, replace
from typing import Any, cast

from devon_ai import contracts as c
from devon_ai.agents.director.agent import _references
from devon_ai.agents.director.runtime import _input_payload, run_director, verification_decision
from devon_ai.llm_tasks.answer_analysis import _check_input, analyze_answer
from devon_ai.llm_tasks.report import _build_inputs, generate_report
from devon_ai.llm_tasks.report_score import check_input
from eval_artifacts import validate_artifacts
from eval_runner import Execution, ExecutionError

from app.llm_tasks.report import validate_draft


def _attempts(items: list[c.AttemptMetadata]) -> tuple[dict[str, Any], ...]:
    result = []
    for item in items:
        record = asdict(item)
        raw = record.pop("raw_output")
        record["raw_output_sha256"] = (
            hashlib.sha256(raw.encode("utf-8")).hexdigest() if raw is not None else None
        )
        try:
            # 원래 byte 지문과 별도로 실제 JSON 내용을 결합한다. 응답 원문은 보존하지 않는다.
            record["raw_output_json_sha256"] = (
                content_hash(_response_json(raw)) if raw is not None else None
            )
        except (ValueError, TypeError, RecursionError):
            record["raw_output_json_sha256"] = None
        if item.schema_version == SOURCE_BOUND_PLAN_SCHEMA:
            # 새 사적 wire만 원문에서 다시 구성한다. 구형 시도 요약의 지문은 바꾸지 않는다.
            record["canonical_question_sha256"] = None
            if raw is not None and item.error_stage is None and item.error_code is None:
                try:
                    question = _source_bound_plan(_response_json(raw), item.prompt_version)
                    record["canonical_question_sha256"] = content_hash(asdict(question))
                except (ValueError, TypeError, RecursionError):
                    pass
        result.append(record)
    return tuple(result)


def _source_bound_plan(raw: object, prompt_version: str) -> c.Question:
    if (
        not plan_schema_matches_version(SOURCE_BOUND_PLAN_SCHEMA, prompt_version)
        or type(raw) is not dict
        or set(raw) != {"question", "intent", "reason_summary"}
        or any(
            type(raw[key]) is not str or not raw[key].strip()
            for key in ("intent", "reason_summary")
        )
    ):
        raise c.ContractError("schema", "source-bound plan receipt")
    return decode_plan_question(raw["question"], prompt_version=prompt_version)


def _object(value: object, name: str) -> dict[str, Any]:
    if type(value) is not dict or any(type(key) is not str for key in value):
        raise ExecutionError("input", name)
    return cast(dict[str, Any], value)


def _locations(raw: object) -> frozenset[tuple[str, str, str]]:
    if type(raw) is not list or any(
        type(item) is not list
        or len(item) != 3
        or any(type(part) is not str or not part.strip() for part in item)
        for item in raw
    ):
        raise ExecutionError("input", "allowed_locations")
    return frozenset(tuple(item) for item in raw)


def _checked_prior_analyses(
    raw: object,
    context: c.Context,
    sources: Mapping[c.BasisRef, str],
    locations: frozenset[tuple[str, str, str]],
) -> tuple[dict[str, c.ContractChecked[c.AnswerAnalysis]], dict[str, c.QuestionContract]]:
    """검증용 과거 계약을 추측하지 않고 당시 발언·현재 원문 범위에 다시 대조한다."""
    supplied = _object(raw, "prior_analyses")
    history = {turn.turn_id: (index, turn) for index, turn in enumerate(context.history)}
    analyses = {}
    contracts = {}
    for turn_id, value in supplied.items():
        if turn_id not in history or turn_id == context.current_turn_id:
            raise ExecutionError("input", "prior_analysis_turn")
        index, turn = history[turn_id]
        if not turn.answer.strip():
            raise ExecutionError("input", "prior_analysis_answer")
        item = _object(value, "prior_analysis")
        if set(item) != {"question_contract", "analysis"}:
            raise ExecutionError("input", "prior_analysis_fields")
        contract = c.decode_strict(c.QuestionContract, item["question_contract"])
        older = {previous.turn_id for previous in context.history[:index]}
        permitted = {ref for ref in sources if ref.kind != "answer_turn" or ref.id in older}
        if not set(contract.basis_refs).issubset(permitted):
            raise ExecutionError("input", "prior_contract_reference")
        checked = c.validate_analysis_for_contract(
            c.decode_strict(c.AnswerAnalysis, item["analysis"]),
            contract=contract,
            answer_text=turn.answer,
            evidence_refs=frozenset(ref.id for ref in sources if ref.kind == "evidence"),
            allowed_locations=locations,
        )
        analyses[turn_id] = checked
        contracts[turn_id] = contract
    return analyses, contracts


def _checked_feedback(raw: object) -> RecoveryFeedback:
    """기존 복구 wire를 같은 runtime 검증기로 읽고 새 승인·참조 권한으로 해석하지 않는다."""
    item = _object(raw, "recovery_feedback")
    if set(item) != {"version", "previous_candidate", "recovery", "review_reason_summary"} or (
        item["version"] != "director-recovery.v1"
    ):
        raise ExecutionError("input", "recovery_feedback_fields")
    return RecoveryFeedback(
        c.decode_strict(c.Question, item["previous_candidate"]),
        c.decode_strict(
            c.CandidateRecovery,
            {"recovery": item["recovery"], "reason_summary": item["review_reason_summary"]},
        ),
    )


def prepare(kind: str, payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """축약 사례에서 당시 질문 계약·원문 버전·정답을 추측해 채우지 않는다."""
    if "service_task" not in payload or "service_input" not in payload:
        raise ExecutionError("input", "explicit_service_input_required")
    if set(payload) != {"service_task", "service_input"}:
        raise ExecutionError("input", "service_envelope")
    task = payload["service_task"]
    if task not in {"director", "director_verification", "answer_analysis", "report"}:
        raise ExecutionError("input", "service_task")
    expected = (
        "report"
        if kind == "report"
        else "director"
        if kind in {"question", "flow"}
        else "answer_analysis"
    )
    if task != expected and not (task == "director_verification" and kind in {"question", "flow"}):
        raise ExecutionError("input", "case_kind_task_mismatch")
    data = _object(payload["service_input"], "service_input")
    if task == "director_verification" and data.get("answer_analysis") is None:
        raise ExecutionError("input", "checked_answer_analysis_required")
    try:
        if task == "report":
            turns, rubric, report = _build_inputs(data)
            check_input(turns, rubric)
            c.validate_report_input(report)
            return task, {"payload": data}
        allowed = {
            "context",
            "question",
            "answer_text",
            "turn_id",
            "allowed_locations",
            "reference_texts",
            "tool_results",
            "answer_analysis",
            "prior_analyses",
            "recovery_feedback",
        }
        if "context" not in data or set(data) - allowed:
            raise ExecutionError("input", "service_input_fields")
        if task != "director" and {"prior_analyses", "recovery_feedback"}.intersection(data):
            raise ExecutionError("input", "director_only_input_fields")
        context = c.decode_strict(c.Context, data["context"])
        references: dict[c.BasisRef, str] = {}
        raw_references = data.get("reference_texts", [])
        if type(raw_references) is not list:
            raise ExecutionError("input", "reference_texts")
        for raw in raw_references:
            item = _object(raw, "reference_texts")
            if set(item) != {"kind", "id", "text"}:
                raise ExecutionError("input", "reference_texts")
            ref = c.decode_strict(c.BasisRef, {"kind": item["kind"], "id": item["id"]})
            if ref in references or type(item["text"]) is not str:
                raise ExecutionError("input", "reference_texts")
            references[ref] = item["text"]
        sources = _references(context, references)
        raw_tools = data.get("tool_results", [])
        if type(raw_tools) is not list:
            raise ExecutionError("input", "tool_results")
        tools = tuple(c.decode_strict(c.ToolResult, item) for item in raw_tools)
        locations = _locations(data.get("allowed_locations", []))
        result: dict[str, Any] = {
            "context": context,
            "reference_texts": references,
            "tool_results": tools,
            "allowed_locations": locations,
        }
        needs_question = task == "answer_analysis" or data.get("answer_analysis") is not None
        if needs_question:
            candidate = c.decode_strict(c.Question, data.get("question"))
            question = c.validate_question(
                candidate,
                review=c.QuestionReview(candidate.text, candidate.question_contract),
                allowed_personas=(candidate.persona,),
                evidence_refs=frozenset(ref.id for ref in sources if ref.kind == "evidence"),
                basis_refs=frozenset(sources),
                jd_requirement_ids=frozenset(item.id for item in context.jd_requirements),
            )
            answer = data.get("answer_text")
            if type(answer) is not str or not answer.strip():
                raise ExecutionError("input", "answer_text")
            result.update(question=question, answer_text=answer)
        if task == "answer_analysis":
            turn_id = data.get("turn_id")
            if type(turn_id) is not str or not turn_id.strip():
                raise ExecutionError("input", "turn_id")
            result["turn_id"] = turn_id
            _check_input(
                context, result["question"], turn_id, result["answer_text"], tools, locations
            )
        elif data.get("answer_analysis") is not None:
            if (
                not context.history
                or context.current_turn_id != context.history[-1].turn_id
                or context.history[-1].question != result["question"].data.text
                or context.history[-1].answer != result["answer_text"]
                or context.current_question_contract != result["question"].data.question_contract
            ):
                raise ExecutionError("input", "current_answer_context_mismatch")
            result["answer_analysis"] = c.validate_analysis(
                c.decode_strict(c.AnswerAnalysis, data["answer_analysis"]),
                question=result["question"],
                answer_text=result["answer_text"],
                evidence_refs=frozenset(ref.id for ref in sources if ref.kind == "evidence"),
                allowed_locations=locations,
            )
        if "prior_analyses" in data:
            result["prior_analyses"], result["prior_question_contracts"] = _checked_prior_analyses(
                data["prior_analyses"], context, sources, locations
            )
        if "recovery_feedback" in data:
            result["recovery_feedback"] = _checked_feedback(data["recovery_feedback"])
        return task, result
    except c.ContractError as exc:
        raise ExecutionError("input", f"contract_{exc.stage}") from None


class ServiceExecutor:
    """모델 함수는 주입하되 운영과 같은 계획·검토·T3·리포트 검증을 실행한다."""

    def __init__(
        self,
        prompts: Mapping[str, c.PromptSpec],
        limits: c.CallLimits,
        model_call_factory: Callable[[], Any],
        *,
        dry_run: bool = False,
        task_limits: Mapping[str, c.CallLimits] | None = None,
    ) -> None:
        self.prompts, self.limits = prompts, limits
        self.model_call_factory, self.dry_run = model_call_factory, dry_run
        self.task_limits = dict(task_limits or {})

    async def __call__(self, kind: str, payload: dict[str, Any]) -> Execution:
        task, data = prepare(kind, payload)
        if task == "director_verification":
            if self.dry_run:
                return Execution({"service_task": task, "input_valid": True}, validated_only=True)
            try:
                decision = verification_decision(
                    data["context"],
                    data["answer_analysis"],
                    allowed_locations=data["allowed_locations"],
                )
            except c.ContractError as error:
                raise ExecutionError(error.stage, "verification_contract_rejected") from None
            return Execution(
                {
                    "decision": c.to_data(decision)
                    if type(decision) is c.ContractChecked
                    else None,
                    "skip_reason": decision if type(decision) is str else None,
                    "execution_scope": "verification_decision_only",
                    "tool_io_executed": False,
                    "next_director_executed": False,
                }
            )
        needed = ("report", "report_score") if task == "report" else (task,)
        if any(name not in self.prompts for name in needed):
            raise ExecutionError("configuration", "prompt_missing")
        if task == "director":
            try:
                _input_payload(
                    data["context"],
                    self.prompts[task],
                    self.limits,
                    data.get("answer_analysis"),
                    data["reference_texts"],
                    data.get("prior_analyses"),
                    data["tool_results"],
                )
            except c.ContractError as exc:
                raise ExecutionError("input", f"director_{exc.stage}") from None
        if self.dry_run:
            return Execution({"service_task": task, "input_valid": True}, validated_only=True)
        attempts: list[c.AttemptMetadata] = []
        director_requests: list[dict[str, Any]] = []
        director_reviews: list[dict[str, Any]] = []
        narrative: c.ReportNarrative | None = None

        def snapshot() -> dict[str, Any] | None:
            return (
                {
                    "schema_version": DIRECTOR_SOURCES_VERSION,
                    "service_input_sha256": content_hash(payload),
                    "requests": copy.deepcopy(director_requests),
                }
                if task == "director" and director_requests
                else None
            )

        def diagnostics() -> dict[str, Any] | None:
            if not director_reviews:
                return None
            return validate_diagnostics(
                {
                    "schema_version": DIRECTOR_DIAGNOSTICS_VERSION,
                    "service_input_sha256": content_hash(payload),
                    "source_snapshot_sha256": content_hash(snapshot()),
                    "reviews": copy.deepcopy(director_reviews),
                },
                service_input_sha256=content_hash(payload),
                source_snapshot=snapshot(),
                attempts=_attempts(attempts),
            )

        def factory() -> Any:
            call = self.model_call_factory()

            async def tracked(request: c.ModelRequest, validator: Any) -> Any:
                nonlocal narrative
                request = replace(
                    request, limits=self.task_limits.get(request.prompt.task_name, request.limits)
                )
                if task == "director":
                    # 실제 실행 경계의 입력을 보존한다. 원래 사례에는 v9가 숨긴 필드가
                    # 있으므로 그것으로 모델의 관찰 범위를 사후 추정하지 않는다.
                    model_payload = json.loads(json.dumps(request.payload, ensure_ascii=False))
                    director_requests.append(
                        {
                            "operation": model_payload.get("operation"),
                            "prompt_version": request.prompt.version,
                            "prompt_template": request.prompt.template,
                            "prompt_template_sha256": hashlib.sha256(
                                request.prompt.template.encode("utf-8")
                            ).hexdigest(),
                            "model": request.prompt.model,
                            "schema_version": request.schema_version,
                            "payload": model_payload,
                            "payload_sha256": content_hash(model_payload),
                        }
                    )
                checked_review: tuple[dict[str, Any], object] | None = None
                checked_plan: object | None = None
                checked_plan_raw: object | None = None

                def tracked_validator(raw: object) -> Any:
                    nonlocal checked_review, checked_plan, checked_plan_raw
                    checked = validator(raw)
                    if task == "director" and request.schema_version == SOURCE_BOUND_PLAN_SCHEMA:
                        canonical = _source_bound_plan(raw, request.prompt.version)
                        if canonical != getattr(checked, "question", None):
                            raise c.ContractError(
                                "semantic", "source-bound plan canonical question"
                            )
                        checked_plan = checked
                        checked_plan_raw = copy.deepcopy(raw)
                    if (
                        task == "director"
                        and request.schema_version in SUPPORTED_REVIEW_SCHEMAS
                        and type(checked) in (c.QuestionReview, c.CandidateRecovery)
                        and type(raw) is dict
                    ):
                        # 원래 검증기가 통과한 결과만 관찰한다. 재검토나 승인 권한은 없다.
                        checked_review = (copy.deepcopy(raw), checked)
                    return checked

                result = await call(request, tracked_validator)
                attempts.extend(result.attempts)
                if (
                    task == "director"
                    and request.schema_version == SOURCE_BOUND_PLAN_SCHEMA
                    and result.failure is None
                ):
                    try:
                        valid = (
                            checked_plan is not None
                            and result.data is checked_plan
                            and len(result.attempts) == 1
                        )
                        if valid:
                            attempt = result.attempts[0]
                            valid = (
                                attempt.error_stage is None
                                and attempt.error_code is None
                                and (attempt.prompt_version, attempt.schema_version)
                                == (request.prompt.version, request.schema_version)
                                and attempt.raw_output is not None
                                and content_hash(_response_json(attempt.raw_output))
                                == content_hash(checked_plan_raw)
                                and _source_bound_plan(
                                    _response_json(attempt.raw_output), request.prompt.version
                                )
                                == getattr(checked_plan, "question", None)
                            )
                    except (ValueError, TypeError, RecursionError):
                        valid = False
                    if not valid:
                        # 검증된 값과 실제 원시 응답이 다르면 Review나 성공 진단을 만들지 않는다.
                        raise ExecutionError("schema", "director_plan_binding_invalid")
                if (
                    checked_review is not None
                    and result.failure is None
                    and result.data is checked_review[1]
                    and len(result.attempts) == 1
                ):
                    attempt = result.attempts[0]
                    raw_text = attempt.raw_output
                    if (
                        raw_text is not None
                        and attempt.error_stage is None
                        and attempt.error_code is None
                        and (attempt.prompt_version, attempt.schema_version)
                        == (request.prompt.version, request.schema_version)
                    ):
                        try:
                            raw_matches = content_hash(json.loads(raw_text)) == content_hash(
                                checked_review[0]
                            )
                        except ValueError:
                            raw_matches = False
                        if raw_matches:
                            observed = director_requests[-1]
                            director_reviews.append(
                                {
                                    "request_index": len(director_requests) - 1,
                                    "attempt_index": len(attempts) - 1,
                                    "request_payload_sha256": observed["payload_sha256"],
                                    "prompt_version": observed["prompt_version"],
                                    "prompt_template_sha256": observed["prompt_template_sha256"],
                                    "response_model": attempt.model,
                                    "response_raw_sha256": hashlib.sha256(
                                        raw_text.encode()
                                    ).hexdigest(),
                                    "assessment": checked_review[0],
                                    "recovery": (
                                        checked_review[1].recovery
                                        if isinstance(checked_review[1], c.CandidateRecovery)
                                        else None
                                    ),
                                }
                            )
                if (
                    request.prompt.task_name == "report"
                    and result.failure is None
                    and type(result.data) is c.ContractChecked
                    and type(result.data.data) is c.ReportNarrative
                ):
                    narrative = result.data.data
                return result

            return tracked

        try:
            if task == "director":
                result = await run_director(
                    data["context"],
                    prompt=self.prompts[task],
                    limits=self.limits,
                    model_call=factory(),
                    answer_analysis=data.get("answer_analysis"),
                    reference_texts=data["reference_texts"],
                    prior_analyses=data.get("prior_analyses"),
                    tool_results=data["tool_results"],
                    recovery_feedback=data.get("recovery_feedback"),
                )
                if result.failure is not None or result.data is None:
                    failure = result.failure
                    raise ExecutionError(
                        failure.stage if failure else "semantic",
                        failure.error_code if failure else "no_output",
                    )
                return Execution(
                    {
                        "decision": asdict(result.data.decision.data),
                        "question": None
                        if result.data.question is None
                        else asdict(result.data.question.data),
                    },
                    _attempts(attempts),
                    source_snapshot={
                        "schema_version": DIRECTOR_SOURCES_VERSION,
                        "service_input_sha256": content_hash(payload),
                        "requests": copy.deepcopy(director_requests),
                    },
                    diagnostics=diagnostics(),
                )
            if task == "answer_analysis":
                answer_result = await analyze_answer(
                    data["context"],
                    data["question"],
                    turn_id=data["turn_id"],
                    answer_text=data["answer_text"],
                    prompt=self.prompts[task],
                    limits=self.limits,
                    model_call=factory(),
                    tool_results=data["tool_results"],
                    allowed_locations=data["allowed_locations"],
                )
                if answer_result.failure is not None or answer_result.data is None:
                    failure = answer_result.failure
                    raise ExecutionError(
                        failure.stage if failure else "semantic",
                        failure.error_code if failure else "no_output",
                    )
                return Execution(asdict(answer_result.data.data), _attempts(attempts))
            raw = await generate_report(
                data["payload"],
                prompts=self.prompts,
                limits=self.limits,
                model_call_factory=factory,
            )
            draft = validate_draft(raw)
            artifacts = None
            if narrative is not None:
                # 실제 모델 결과의 검증된 Claim만 보존한다. 공개 문자열에서 참조를 추측하지 않는다.
                _, _, report_input = _build_inputs(data["payload"])
                c.validate_narrative(narrative, report_input=report_input)
                artifacts = _narrative_artifacts(narrative)
            return Execution(
                {
                    "totalScore": draft.total_score,
                    "scores": [
                        {"key": key, "score": value.score} for key, value in draft.scores.items()
                    ],
                    "headline": draft.headline,
                    "summary": draft.summary,
                    "feedbacks": [asdict(item) for item in draft.feedbacks],
                },
                _attempts(attempts),
                artifacts=artifacts,
            )
        except ExecutionError as exc:
            raise ExecutionError(
                exc.stage,
                exc.code,
                _attempts(attempts),
                source_snapshot={
                    "schema_version": DIRECTOR_SOURCES_VERSION,
                    "service_input_sha256": content_hash(payload),
                    "requests": copy.deepcopy(director_requests),
                }
                if task == "director" and director_requests
                else None,
                diagnostics=diagnostics(),
            ) from None
        except c.ContractError as exc:
            raise ExecutionError(
                exc.stage,
                "service_contract_rejected",
                _attempts(attempts),
                source_snapshot=snapshot(),
                diagnostics=diagnostics(),
            ) from None
        except Exception as exc:
            raise ExecutionError(
                "executor",
                type(exc).__name__,
                _attempts(attempts),
                source_snapshot=snapshot(),
                diagnostics=diagnostics(),
            ) from None
        except BaseException as exc:
            # 취소 예외의 종류는 보존하고 완료한 시도·실제 요청만 사적 checkpoint에 전달한다.
            exc.__dict__.update(
                attempts=_attempts(attempts), source_snapshot=snapshot(), diagnostics=diagnostics()
            )
            raise


def _narrative_artifacts(narrative: c.ReportNarrative) -> dict[str, object]:
    claims: list[dict[str, object]] = []

    def append(section: str, persona: str | None, entries: tuple[c.NarrativeClaim, ...]) -> None:
        claims.extend(
            {
                "section": section,
                "persona": persona,
                "claim_index": index,
                "text": item.text,
                "turn_refs": list(item.turn_refs),
                "evidence_refs": list(item.evidence_refs),
            }
            for index, item in enumerate(entries)
        )

    if narrative.summary.overview is not None:
        append("summary.overview", None, (narrative.summary.overview,))
    for name in ("strengths", "gaps", "follow_ups", "practice_actions"):
        append(f"summary.{name}", None, getattr(narrative.summary, name))
    for item in narrative.persona_feedbacks:
        for name in ("strengths", "improvements", "practice_actions"):
            append(name, item.persona, getattr(item, name))
    return validate_artifacts({"schema_version": "validated-report-claims.v1", "claims": claims})
