"""고정 원문의 AI 코어 9턴 실행. REST·DB·WS·Tool I/O를 실행했다고 주장하지 않는다.

ServiceExecutor의 실제 Director/T3 경로를 사용한다. 답변은 실제 생성 질문의
hash에 결합한 외부 입력으로 받으며, 모델 답변 생성기를 기본으로 추가하지 않는다.
"""

from __future__ import annotations

import copy
import json
import time
from collections import Counter
from collections.abc import Awaitable, Callable
from dataclasses import asdict, replace
from typing import Any, cast

from devon_ai import contracts as c
from director_cases import content_hash
from eval_cases import Case
from eval_runner import Execution, ExecutionError

from app.features.interview.evaluation_coverage import (
    plan_evaluation_targets,
    presented_evaluation_keys,
)

QUOTA = {"hr_manager": 1, "tech_lead": 6, "domain_lead": 2}
FORMAT = "director-trajectory.v1"
Checkpoint = Callable[[dict[str, Any]], Awaitable[None]]
Executor = Callable[[str, dict[str, Any]], Awaitable[Execution]]


def _wire(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))


def _seal(state: dict[str, Any]) -> dict[str, Any]:
    state["state_sha256"] = content_hash(
        {key: value for key, value in state.items() if key != "state_sha256"}
    )
    return state


def _validate(state: dict[str, Any]) -> None:
    if state.get("format_version") != FORMAT or state.get("state_sha256") != content_hash(
        {key: value for key, value in state.items() if key != "state_sha256"}
    ):
        raise ValueError("trajectory state binding mismatch")
    if state.get("materials_sha256") != content_hash(state.get("materials")):
        raise ValueError("trajectory material binding mismatch")
    turns = state.get("turns")
    if not isinstance(turns, list) or len(turns) > 9:
        raise ValueError("invalid trajectory turns")


def create_trajectory(case: Case, *, session_id: str) -> dict[str, Any]:
    if not isinstance(session_id, str) or not session_id.strip():
        raise ValueError("trajectory needs a session ID")
    data = case.payload["service_input"]
    context = c.decode_strict(c.Context, data["context"])
    normalized = _wire(asdict(context))
    materials = {
        name: copy.deepcopy(normalized[name])
        for name in (
            "jd_requirements",
            "repositories",
            "evidence",
            "domain_frames",
            "supplemental_sources",
            "external_searches",
            "supplemental_limitations",
        )
    }
    materials["reference_texts"] = copy.deepcopy(data.get("reference_texts", []))
    materials["allowed_locations"] = copy.deepcopy(data.get("allowed_locations", []))
    # 실제·합성 원문을 모두 내부 타입으로 읽고 생략 가능한 목록은 계약의 기본값을 따른다.
    if not context.repositories:
        raise ValueError("trajectory needs bound source material")
    return _seal(
        {
            "format_version": FORMAT,
            "session_id": session_id,
            "source_case": f"{case.case_id}.v{case.version}",
            "source_group_id": case.source_group_id,
            "source_payload_sha256": content_hash(case.payload),
            "materials": materials,
            "materials_sha256": content_hash(materials),
            "status": "ready",
            "turns": [],
            "executions": [],
            "normal_model_attempts": 27,
            "scope": {
                "service_ai_core_executed": False,
                "database_executed": False,
                "websocket_executed": False,
                "tool_io_executed": False,
                "answer_origin": "synthetic_codex",
                "human_review_status": "deferred",
            },
            "limitations": [
                "텍스트 AI 코어의 9턴 경로이며 실제 DB·WS·Tool I/O 검증을 대체하지 않는다.",
                "합성 답변은 실제 생성된 질문 hash에 결합해야 하며 개인 역량의 증거가 아니다.",
            ],
        }
    )


def _context(state: dict[str, Any], *, answering: bool) -> c.Context:
    turns = state["turns"]
    answered = [turn for turn in turns if turn["analysis"] is not None]
    contracts = tuple(
        c.decode_strict(c.Question, turn["question"]).question_contract for turn in turns
    )
    counts = Counter(turn["question"]["persona"] for turn in turns)
    permitted: tuple[c.PersonaId, ...] = cast(
        tuple[c.PersonaId, ...],
        tuple(
            persona
            for persona in ("hr_manager", "tech_lead", "domain_lead")
            if counts[persona] < QUOTA[persona]
        ),
    )
    if not turns:
        permitted = ("hr_manager",)
    current = turns[-1] if turns else None
    materials = state["materials"]
    raw = {
        name: copy.deepcopy(materials[name])
        for name in (
            "jd_requirements",
            "repositories",
            "evidence",
            "domain_frames",
            "supplemental_sources",
            "external_searches",
            "supplemental_limitations",
        )
    }
    raw.update(
        interview_id=state["session_id"],
        current_turn_id=current["turn_id"] if current else None,
        turn_no=len(turns) if answering else len(answered) + 1,
        total_turns=9,
        persona_counts=[{"persona": persona, "count": counts[persona]} for persona in QUOTA],
        allowed_personas=list(permitted),
        history=[
            {
                "turn_id": turn["turn_id"],
                "persona": turn["question"]["persona"],
                "question": turn["question"]["text"],
                "answer": turn["answer"]["text"],
                "analysis_ref": turn["turn_id"],
            }
            for turn in answered
        ],
        current_question_contract=current["question"]["question_contract"] if current else None,
        limits={"remaining_calls": 2, "remaining_replans": 0, "policy_version": FORMAT},
        evaluation_targets=[]
        if answering
        else [
            asdict(target)
            for target in plan_evaluation_targets(
                contracts, permitted, has_jd=bool(materials["jd_requirements"])
            )
        ],
        presented_evaluation_keys=list(presented_evaluation_keys(contracts)),
    )
    return c.decode_strict(c.Context, _wire(raw))


async def _checkpoint(state: dict[str, Any], checkpoint: Checkpoint | None) -> dict[str, Any]:
    _seal(state)
    if checkpoint is not None:
        await checkpoint(copy.deepcopy(state))
    return state


async def _execute(
    state: dict[str, Any],
    executor: Executor,
    task: str,
    payload: dict[str, Any],
    *,
    checkpoint: Checkpoint | None = None,
) -> Execution | None:
    started = time.perf_counter()
    event: dict[str, Any] = {"task": task, "input_sha256": content_hash(payload)}
    try:
        result = await executor("question" if task == "director" else "evidence", _wire(payload))
        result = replace(result, output=_wire(result.output))
    except ExecutionError as error:
        event.update(
            status="failed",
            error_stage=error.stage,
            error_code=error.code,
            attempts=list(error.attempts),
            source_snapshot=error.source_snapshot,
        )
        if error.diagnostics is not None:
            event.update(
                diagnostics=copy.deepcopy(error.diagnostics),
                diagnostics_hash=content_hash(error.diagnostics),
            )
        state["status"] = "failed"
        return None
    except BaseException as error:
        event.update(
            status="interrupted",
            error_code=type(error).__name__,
            attempts=list(getattr(error, "attempts", ())),
            source_snapshot=copy.deepcopy(getattr(error, "source_snapshot", None)),
        )
        diagnostics = getattr(error, "diagnostics", None)
        if diagnostics is not None:
            event.update(
                diagnostics=copy.deepcopy(diagnostics), diagnostics_hash=content_hash(diagnostics)
            )
        state["status"] = "interrupted"
        raise
    else:
        event.update(
            status="validated_only" if result.validated_only else "succeeded",
            output=copy.deepcopy(result.output),
            attempts=list(result.attempts),
            source_snapshot=copy.deepcopy(result.source_snapshot),
        )
        if result.diagnostics is not None:
            event.update(
                diagnostics=copy.deepcopy(result.diagnostics),
                diagnostics_hash=content_hash(result.diagnostics),
            )
        state["scope"]["service_ai_core_executed"] = not result.validated_only
        if result.validated_only:
            state["status"] = "validated_only"
            return None
        return result
    finally:
        event["service_latency_ms"] = round((time.perf_counter() - started) * 1000)
        state["executions"].append(event)
        if event.get("status") == "interrupted":
            await _checkpoint(state, checkpoint)


async def advance(
    state: dict[str, Any],
    executor: Executor,
    *,
    answer: dict[str, Any] | None = None,
    checkpoint: Checkpoint | None = None,
) -> dict[str, Any]:
    """질문 한 개 또는 실제 질문에 결합한 답변 한 개를 처리하고 보존한다."""
    _validate(state)
    state = copy.deepcopy(state)
    if state["status"] in {"completed", "requires_tools", "failed", "validated_only"}:
        if answer is not None:
            raise ValueError("trajectory is not accepting an answer")
        return state
    if state["status"] not in {"ready", "awaiting_answer", "ready_for_question"}:
        raise ValueError("in-flight trajectory requires call audit before resuming")
    if state["status"] == "awaiting_answer":
        if answer is None:
            return state
        pending = state["turns"][-1]
        if (
            set(answer) != {"question_sha256", "text", "origin"}
            or answer["question_sha256"] != content_hash(pending["question"])
            or not isinstance(answer["text"], str)
            or not answer["text"].strip()
            or answer["origin"] != "synthetic_codex"
        ):
            raise ValueError("answer must bind to the actual question and declared origin")
        pending["answer"] = copy.deepcopy(answer)
        context = _context(state, answering=True)
        data = {
            "context": asdict(context),
            "question": pending["question"],
            "turn_id": pending["turn_id"],
            "answer_text": answer["text"],
            "reference_texts": state["materials"]["reference_texts"],
            "allowed_locations": state["materials"]["allowed_locations"],
            "tool_results": [],
        }
        state["status"] = "analyzing_answer"
        await _checkpoint(state, checkpoint)
        result = await _execute(
            state,
            executor,
            "answer_analysis",
            {"service_task": "answer_analysis", "service_input": data},
            checkpoint=checkpoint,
        )
        if result is None:
            return await _checkpoint(state, checkpoint)
        pending["analysis"] = copy.deepcopy(result.output)
        analysis = c.decode_strict(c.AnswerAnalysis, result.output)
        final_answer = len(state["turns"]) == 9
        if analysis.verification_requests or (analysis.external_queries and not final_answer):
            state["status"] = "requires_tools"
            return await _checkpoint(state, checkpoint)
        if final_answer:
            if analysis.external_queries:
                # 운영 Controller와 같이 마지막 확정 답변 뒤 새 외부 탐색을 시작하지 않는다.
                # 원래 요청은 분석에 보존하고 검색 미실행을 성공·미발견으로 바꾸지 않는다.
                trace = c.ExternalSearchStatus(
                    "insufficient_analysis",
                    (),
                    (),
                    ("external_lookup_not_executed:final_turn",),
                    "final_turn_lookup_not_executed",
                )
                state["external_searches"] = [
                    *state.get("external_searches", state["materials"]["external_searches"]),
                    _wire(asdict(trace)),
                ]
                state["limitations"].append("external_lookup_not_executed:final_turn")
            state["status"] = "completed"
            return await _checkpoint(state, checkpoint)
        state["status"] = "ready_for_question"
        await _checkpoint(state, checkpoint)
    elif answer is not None:
        raise ValueError("no generated question is waiting for this answer")
    context = _context(state, answering=False)
    data = {
        "context": asdict(context),
        "reference_texts": state["materials"]["reference_texts"],
        "allowed_locations": state["materials"]["allowed_locations"],
        "tool_results": [],
    }
    if state["turns"]:
        previous = state["turns"][-1]
        data.update(
            question=previous["question"],
            answer_text=previous["answer"]["text"],
            answer_analysis=previous["analysis"],
        )
    state["status"] = "generating_question"
    await _checkpoint(state, checkpoint)
    result = await _execute(
        state,
        executor,
        "director",
        {"service_task": "director", "service_input": data},
        checkpoint=checkpoint,
    )
    if result is None:
        return await _checkpoint(state, checkpoint)
    output = cast(dict[str, Any], result.output)
    question = c.decode_strict(c.Question, output["question"])
    state["turns"].append(
        {
            "turn_id": f"{state['session_id']}-t{len(state['turns']) + 1}",
            "question": _wire(asdict(question)),
            "answer": None,
            "analysis": None,
        }
    )
    state["status"] = "awaiting_answer"
    return await _checkpoint(state, checkpoint)
