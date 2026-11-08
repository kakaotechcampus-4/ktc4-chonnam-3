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
        result.append(record)
    return tuple(result)


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
        }
        if "context" not in data or set(data) - allowed:
            raise ExecutionError("input", "service_input_fields")
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
                    None,
                    data["tool_results"],
                )
            except c.ContractError as exc:
                raise ExecutionError("input", f"director_{exc.stage}") from None
        if self.dry_run:
            return Execution({"service_task": task, "input_valid": True}, validated_only=True)
        attempts: list[c.AttemptMetadata] = []
        narrative: c.ReportNarrative | None = None

        def factory() -> Any:
            call = self.model_call_factory()

            async def tracked(request: c.ModelRequest, validator: Any) -> Any:
                nonlocal narrative
                request = replace(
                    request, limits=self.task_limits.get(request.prompt.task_name, request.limits)
                )
                result = await call(request, validator)
                attempts.extend(result.attempts)
                if (
                    request.prompt.task_name == "report"
                    and result.failure is None
                    and type(result.data) is c.ContractChecked
                    and type(result.data.data) is c.ReportNarrative
                ):
                    narrative = result.data.data
                return result

            return tracked

