from app.integrations.execution_ledger import (  # noqa: E402
    ExecutionLedger,
    execution_scope,
    observe_call,
)
from scripts.ai_eval_bridge import ServiceExecutor, prepare  # noqa: E402
from scripts.evaluation_output import RunOutput, technical_exit_code  # noqa: E402
from scripts.run_ai_evaluation import (  # noqa: E402
    ModelAttemptBudget,
    load_manifest,
    source_metadata,
)

LUNA = "gpt-6-luna"


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--manifest", type=Path)
    value.add_argument("--selection", choices=("pilot", "dev", "holdout", "all"), default="pilot")
    value.add_argument("--case-id", action="append", default=[])
    value.add_argument("--output", type=Path, required=True)
    value.add_argument("--execute", action="store_true")
    value.add_argument("--max-model-attempts", type=int)
    value.add_argument("--max-wall-seconds", type=float)
    value.add_argument("--env-file", type=Path)
    value.add_argument("--ledger", type=Path)
    value.add_argument("--export-cases", type=Path)
    value.add_argument("--export-review-packets", type=Path)
    value.add_argument("--controls-only", action="store_true")
    value.add_argument("--rejudge-results", type=Path)
    value.add_argument("--recorded-judgments", type=Path)
    value.add_argument("--compare", type=Path, nargs=2, metavar=("BASELINE", "CANDIDATE"))
    return value


def luna_factory(
    factory: Callable[[], Any], limits: c.CallLimits | Mapping[str, c.CallLimits]
) -> Callable[[], Any]:
    """실제 요청·응답 모델과 설정을 검사한다. 불일치에도 사용한 시도는 남긴다."""

    def call() -> Any:
        invoke = None

        async def guarded(request: c.ModelRequest, validator: Any) -> Any:
            nonlocal invoke
            if request.prompt.model != LUNA:
                return c.ModelResult(
                    None,
                    c.CallFailure("semantic", "director_study_model_mismatch", "Luna required."),
                    (),
                )
            expected = (
                limits if isinstance(limits, c.CallLimits) else limits.get(request.prompt.task_name)
            )
            if request.limits != expected:
                return c.ModelResult(
                    None,
                    c.CallFailure(
                        "semantic", "director_study_settings_mismatch", "Settings changed."
                    ),
                    (),
                )
            if invoke is None:
                invoke = factory()
            operation = request.payload.get("operation", request.prompt.task_name)
            async with observe_call(f"director.{operation}", kind="stage") as observation:
                result = await invoke(request, validator)
                if any(attempt.model != LUNA for attempt in result.attempts):
                    result = c.ModelResult(
                        None,
                        c.CallFailure(
                            "semantic",
                            "director_study_model_mismatch",
                            "Unexpected response model.",
                        ),
                        result.attempts,
                    )
                if observation is not None:
                    observation.complete(result.failure.error_code if result.failure else None)
                return result

        return guarded

    return call


def _write_new(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


async def execute(args: argparse.Namespace) -> dict[str, Any]:
    if args.compare is not None:
        if args.execute or args.rejudge_results or args.controls_only:
            raise ValueError("comparison cannot execute models")
        baseline, candidate = (
            json.loads(path.read_text(encoding="utf-8")) for path in args.compare
        )
        result = compare_runs(baseline, candidate)
        _write_new(args.output, result)
        return result
    cohort = build_cohort()
    if args.export_cases:
        export_cohort(cohort, args.export_cases)
    if args.controls_only:
        if args.execute or args.rejudge_results:
            raise ValueError("control packet export cannot execute models")
        packets, labels = control_packets(cohort)
        result = {
            "format_version": 1,
            "scope": "grader_controls_only",
            "packets": packets,
            "labels_sha256": content_hash(labels),
            "model_api_calls": 0,
        }
        _write_new(args.output, result)
        _write_new(args.output.with_suffix(".labels.json"), labels)
        return result
    if args.execute and (
        type(args.max_model_attempts) is not int
        or args.max_model_attempts < 1
        or type(args.max_wall_seconds) not in {float, int}
        or not math.isfinite(args.max_wall_seconds)
        or args.max_wall_seconds <= 0
    ):
        raise ValueError("live execution requires attempt and wall budgets")
    if args.rejudge_results is not None and (args.execute or args.recorded_judgments is None):
        raise ValueError("rejudge requires only recorded judgments")
    if args.recorded_judgments is not None and args.rejudge_results is None:
        raise ValueError("recorded judgments require original results")
    if args.manifest is None:
        raise ValueError("Director study requires a manifest")
    prompts, limits, prompt_metadata = load_manifest(args.manifest)
    if set(prompts) != {"director"} or prompts["director"].model != LUNA:
        raise ValueError("Director study requires one Luna Director prompt")
    task_limits = {
        task: replace(limits, **values) for task, values in prompt_metadata["task_limits"].items()
    }
    effective_limits = task_limits.get("director", limits)
    cases = list(cohort.select(args.selection))
    if args.case_id:
        chosen = set(args.case_id)
        if len(chosen) != len(args.case_id) or not chosen <= {case.case_id for case in cases}:
            raise ValueError("unknown or duplicate case selection")
        cases = [case for case in cases if case.case_id in chosen]
    for case in cases:
        prepare(case.kind, case.model_input())
    run_id = str(uuid4())
    metadata = {
        **source_metadata(),
        **prompt_metadata,
        "study": {
            "version": cohort.manifest["version"],
            "selection": args.selection,
            "cohort_sha256": content_hash(cohort.manifest),
            "settings_sha256": content_hash({"model": LUNA, "limits": asdict(effective_limits)}),
            "source_groups": len({case.source_group_id for case in cases}),
            "synthetic": True,
            "run_id": run_id,
            "model_api_calls": 0 if not args.execute else None,
            "max_model_attempts": args.max_model_attempts,
            "max_wall_seconds": args.max_wall_seconds,
            "human_review_status": "deferred",
            "rubric_protocol": cohort.manifest["rubric_protocol"],
        },
    }
    if args.rejudge_results is not None:
        original_bytes = args.rejudge_results.read_bytes()
        previous = json.loads(original_bytes)
        if previous.get("run_state") != "completed":
            raise ValueError("original study must be completed")
        for key in ("cohort_sha256", "settings_sha256"):
            if previous.get("metadata", {}).get("study", {}).get(key) != metadata["study"][key]:
                raise ValueError("original study binding mismatch")
        grader = RecordedGrader.from_path(args.recorded_judgments)
        started = time.perf_counter()
        judgment = await rejudge_cases(cases, previous, grader, metadata=metadata)
        result = copy.deepcopy(previous)
        judgments = {row["case"]: row.get("judge") for row in judgment["cases"]}
        for row in result["cases"]:
            row["diagnostic_judge"] = judgments[row["case"]]
        result["recorded_judge_audit"] = grader.records
        result["recorded_evaluation"] = {
            "source_results_sha256": hashlib.sha256(original_bytes).hexdigest(),
            "recorded_document_sha256": grader.document_sha256,
            "elapsed_ms": round((time.perf_counter() - started) * 1000),
            "service_model_calls": 0,
            "original_review_usage": "not_collected",
            "summary": judgment["summary"],
            "human_review_status": "deferred",
        }
        writer = RunOutput(args.output)
        writer.save(result, "completed")
        return result
    settings = (
        (Settings(_env_file=args.env_file) if args.env_file else get_settings()).require_llm()
        if args.execute
        else None
    )
    if settings is not None:
        if settings.llm_default_model != LUNA:
            raise ValueError("environment must select Luna before execution")
        if settings.call_limits("director") != effective_limits:
            raise ValueError("manifest must preserve current environment limits")

    def unused_factory() -> Any:
        raise RuntimeError("validation must not call a model")

    budget = ModelAttemptBudget(args.max_model_attempts, settings) if args.execute else None
    factory = (
        luna_factory(budget.factory, effective_limits) if budget is not None else unused_factory
    )
    executor = ServiceExecutor(
        prompts, limits, factory, dry_run=not args.execute, task_limits=task_limits
    )
    writer = RunOutput(args.output)
    ledger = (
        ExecutionLedger(args.ledger or args.output.with_suffix(".ledger.sqlite3"))
        if args.execute
        else None
    )
    try:
        if ledger is not None:

            async def tracked(kind: str, payload: dict[str, Any]) -> Any:
                with execution_scope(
                    ledger,
                    run_id=run_id,
                    entrypoint="director_study",
                    metadata={
                        "case_id": payload["service_input"]["context"]["interview_id"],
                        "cohort": args.selection,
                    },
                ):
                    async with observe_call("director_case", kind="stage"):
                        return await executor(kind, payload)

            async with asyncio.timeout(args.max_wall_seconds):
                result = await run_cases(
                    cases, tracked, metadata=metadata, checkpoint=writer.checkpoint
                )
            admissions = [
                record
                for record in ledger.records()
                if record.run_id == run_id and record.kind == "generation"
            ]
            result["metadata"]["study"].update(
                model_api_calls=len(admissions),
                ledger=str(ledger.path),
                unknown_response_models=sum(record.actual_model is None for record in admissions),
            )
        else:
            result = await run_cases(
                cases, executor, metadata=metadata, checkpoint=writer.checkpoint
            )
        if args.export_review_packets:
            _write_new(
                args.export_review_packets,
                {"format_version": 1, "packets": review_packets(cases, result)},
            )
        writer.save(result, "completed")
        return result
    except BaseException as error:
        writer.stop(
            "interrupted" if isinstance(error, asyncio.CancelledError) else "failed",
            type(error).__name__,
        )
        raise


def main() -> int:
    args = parser().parse_args()
    try:
        result = asyncio.run(execute(args))
    except Exception as error:
        print(json.dumps({"status": "failed", "error_code": type(error).__name__}))
        return 1
    print(json.dumps({"status": "completed", "output": str(args.output)}, ensure_ascii=False))
    return technical_exit_code(result) if "cases" in result else 0


if __name__ == "__main__":
    raise SystemExit(main())
