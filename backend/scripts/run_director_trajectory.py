from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import re
import sys
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parents[2]
for folder in (REPO_ROOT / "ai" / "evals", REPO_ROOT / "ai" / "src", REPO_ROOT / "backend"):
    sys.path.insert(0, str(folder))

from director_cases import build_cohort, content_hash  # noqa: E402
from eval_cases import (  # noqa: E402
    _EXPECTATION_KEYS,
    _EXPECTATION_OPTIONAL,
    Case,
    _check_expectation,
    _check_keys,
)

from app.core.config import Settings, get_settings  # noqa: E402
from app.integrations.execution_ledger import ExecutionLedger, execution_scope  # noqa: E402
from scripts.ai_eval_bridge import ServiceExecutor, prepare  # noqa: E402
from scripts.director_trajectory import advance, create_trajectory  # noqa: E402
from scripts.evaluation_output import RunOutput  # noqa: E402
from scripts.run_ai_evaluation import (  # noqa: E402
    ModelAttemptBudget,
    load_manifest,
    source_metadata,
)
from scripts.run_director_study import LUNA, luna_factory  # noqa: E402

MAX_SEED_BYTES = 512 * 1024
_SEED_FIELDS = {"case_id", "version", "kind", "split", "source_group_id", "payload", "expectation"}


def _unique_seed_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate seed JSON key")
        result[key] = value
    return result


def load_seed_file(path: Path, expected_sha256: str | None = None) -> tuple[Case, dict[str, Any]]:
    """파일 지문과 실제 typed 입력을 검사한다. 수집 원천의 진실성은 별도 provenance로 확인한다."""
    with path.open("rb") as stream:
        raw = stream.read(MAX_SEED_BYTES + 1)
    if not raw or len(raw) > MAX_SEED_BYTES:
        raise ValueError("seed file byte limit exceeded")
    digest = hashlib.sha256(raw).hexdigest()
    if expected_sha256 is not None and (
        re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is None or digest != expected_sha256
    ):
        raise ValueError("seed file hash mismatch")
    try:
        data = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_unique_seed_keys)
    except (UnicodeError, ValueError, RecursionError):
        raise ValueError("invalid seed JSON") from None
    if not isinstance(data, dict) or set(data) != _SEED_FIELDS:
        raise ValueError("seed requires exactly the seven Case fields")
    if (
        any(
            not isinstance(data[key], str) or not data[key].strip() or len(data[key]) > 200
            for key in ("case_id", "source_group_id")
        )
        or type(data["version"]) is not int
        or data["version"] < 1
        or data["kind"] != "question"
        or not isinstance(data["split"], str)
        or data["split"] not in {"dev", "holdout"}
        or not isinstance(data["payload"], dict)
        or not isinstance(data["expectation"], dict)
    ):
        raise ValueError("invalid seed Case fields")
    expectation = data["expectation"]
    _check_keys("seed expectation", expectation, _EXPECTATION_KEYS, _EXPECTATION_OPTIONAL)
    _check_expectation("seed expectation", expectation)
    if (
        expectation["case_id"] != data["case_id"]
        or type(expectation["version"]) is not int
        or expectation["version"] != data["version"]
        or "pair" in expectation
    ):
        raise ValueError("seed expectation binding mismatch")
    case = Case(**data)
    task, prepared = prepare(case.kind, case.model_input())
    if task != "director":
        raise ValueError("trajectory seed must contain a typed Director input")
    context = prepared["context"]
    if (
        len(context.repositories) != 1
        or not context.repositories[0].primary
        or not context.evidence
    ):
        raise ValueError("seed requires one primary repository and bound original evidence")
    repository = context.repositories[0]
    if any(
        (item.repository_id, item.git_ref) != (repository.repository_id, repository.git_ref)
        for item in context.evidence
    ):
        raise ValueError("seed mixes evidence source versions")
    if any(
        (repo, git_ref) != (repository.repository_id, repository.git_ref)
        for repo, git_ref, _ in prepared["allowed_locations"]
    ):
        raise ValueError("seed mixes allowed location versions")
    return case, {
        "path": str(path.resolve()),
        "sha256": digest,
        "bytes": len(raw),
        "payload_sha256": content_hash(case.payload),
        "case": f"{case.case_id}.v{case.version}",
        "provenance_verified": False,
    }


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--manifest", type=Path, required=True)
    seed = value.add_mutually_exclusive_group()
    seed.add_argument("--seed-case-id")
    seed.add_argument("--seed-file", type=Path)
    value.add_argument("--seed-sha256")
    value.add_argument("--session-id")
    value.add_argument("--resume", type=Path)
    value.add_argument("--answer-file", type=Path)
    value.add_argument("--output", type=Path, required=True)
    value.add_argument("--execute", action="store_true")
    value.add_argument("--env-file", type=Path)
    value.add_argument("--max-model-attempts", type=int)
    value.add_argument("--max-session-attempts", type=int, default=36)
    value.add_argument("--max-wall-seconds", type=float)
    value.add_argument("--ledger", type=Path)
    return value


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
