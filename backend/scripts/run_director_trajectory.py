async def execute(args: argparse.Namespace) -> dict[str, Any]:
    if args.execute and (
        type(args.max_model_attempts) is not int
        or args.max_model_attempts < 1
        or type(args.max_wall_seconds) not in {int, float}
        or not math.isfinite(args.max_wall_seconds)
        or args.max_wall_seconds <= 0
    ):
        raise ValueError("execution requires finite attempt and wall budgets")
    if type(args.max_session_attempts) is not int or args.max_session_attempts < 1:
        raise ValueError("session attempt budget must be positive")
    prompts, limits, prompt_metadata = load_manifest(args.manifest)
    if set(prompts) != {"director", "answer_analysis"} or any(
        prompt.model != LUNA for prompt in prompts.values()
    ):
        raise ValueError("trajectory requires Luna Director and T3 prompts")
    task_limits = {
        task: replace(limits, **values) for task, values in prompt_metadata["task_limits"].items()
    }
    expected_limits = {task: task_limits.get(task, limits) for task in prompts}
    experiment_hash = content_hash(
        {
            "prompts": prompt_metadata["prompts"],
            "limits": {task: asdict(value) for task, value in expected_limits.items()},
            "max_session_attempts": args.max_session_attempts,
        }
    )
    if args.resume:
        if args.seed_case_id or args.seed_file or args.seed_sha256 or args.session_id:
            raise ValueError("resume cannot replace session source or identity")
        previous = json.loads(args.resume.read_text(encoding="utf-8"))
        if (
            previous.get("run_state") != "completed"
            or previous.get("metadata", {}).get("experiment_sha256") != experiment_hash
        ):
            raise ValueError("resume requires completed step with unchanged prompts and limits")
        state = previous["trajectory"]
        seed_metadata = previous.get("metadata", {}).get("seed_file")
    else:
        if args.answer_file or not (args.seed_case_id or args.seed_file) or not args.session_id:
            raise ValueError("new trajectory requires source case and session identity")
        if args.seed_file:
            case, seed_metadata = load_seed_file(args.seed_file, args.seed_sha256)
        else:
            if args.seed_sha256:
                raise ValueError("seed hash requires a seed file")
            cases = {case.case_id: case for case in build_cohort().cases}
            if args.seed_case_id not in cases:
                raise ValueError("unknown trajectory source case")
            case, seed_metadata = cases[args.seed_case_id], None
        state = create_trajectory(case, session_id=args.session_id)
    answer = json.loads(args.answer_file.read_text(encoding="utf-8")) if args.answer_file else None
    attempted = sum(len(event.get("attempts", [])) for event in state["executions"])
    remaining = args.max_session_attempts - attempted
    if (
        args.execute
        and remaining < 1
        and state["status"] not in {"completed", "requires_tools", "failed"}
    ):
        raise ValueError("session attempt budget exhausted")
    settings = (
        (Settings(_env_file=args.env_file) if args.env_file else get_settings()).require_llm()
        if args.execute
        else None
    )
    if settings is not None:
        if settings.llm_default_model != LUNA:
            raise ValueError("environment must select Luna")
        if any(settings.call_limits(task) != value for task, value in expected_limits.items()):
            raise ValueError("manifest must preserve environment task limits")

    def unused() -> Any:
        raise RuntimeError("validation must not call providers")

    maximum = min(args.max_model_attempts, remaining) if args.execute else 0
    budget = ModelAttemptBudget(maximum, settings) if args.execute and maximum > 0 else None
    factory = luna_factory(budget.factory, expected_limits) if budget is not None else unused
    executor = ServiceExecutor(
        prompts, limits, factory, dry_run=not args.execute, task_limits=task_limits
    )
    metadata = {
        **source_metadata(),
        **prompt_metadata,
        "experiment_sha256": experiment_hash,
        "scope": "ai_core_trajectory_only",
        "model_api_calls": 0 if not args.execute else None,
        "max_session_attempts": args.max_session_attempts,
        "remaining_before_step": remaining,
        "max_step_attempts": maximum,
        "max_wall_seconds": args.max_wall_seconds,
        "human_review_status": "deferred",
        "seed_file": seed_metadata,
    }
    writer = RunOutput(args.output)

    async def checkpoint(current: dict[str, Any]) -> None:
        await writer.checkpoint({"metadata": metadata, "trajectory": current})

    try:
        if args.execute:
            ledger = ExecutionLedger(args.ledger or args.output.with_suffix(".ledger.sqlite3"))
            run_id = str(uuid4())
            with execution_scope(
                ledger,
                run_id=run_id,
                entrypoint="director_trajectory",
                metadata={
                    "interview_id": state["session_id"],
                    "turn": len(state["turns"]),
                },
            ):
                async with asyncio.timeout(args.max_wall_seconds):
                    state = await advance(state, executor, answer=answer, checkpoint=checkpoint)
            metadata.update(
                model_api_calls=sum(
                    record.run_id == run_id and record.kind == "generation"
                    for record in ledger.records()
                ),
                ledger=str(ledger.path),
                run_id=run_id,
            )
        else:
            state = await advance(state, executor, answer=answer, checkpoint=checkpoint)
        result = {"metadata": metadata, "trajectory": state}
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
    state = result["trajectory"]
    print(
        json.dumps(
            {"status": state["status"], "turns": len(state["turns"]), "output": str(args.output)}
        )
    )
    return 0 if state["status"] in {"awaiting_answer", "completed", "validated_only"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
