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
