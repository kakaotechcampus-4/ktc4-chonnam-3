"""명시적 입력·모델·시도 예산으로 실행하는 로컬 AI 평가 CLI.

기본은 API를 호출하지 않는 입력 검증이다. 실제 실행은 --execute와
--max-model-attempts가 모두 필요하며 검수 전 사례는 품질 통과로 계산하지 않는다.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib
import json
import subprocess
import sys
from dataclasses import asdict, fields, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "ai" / "evals"))
sys.path.insert(0, str(REPO_ROOT / "ai" / "src"))
sys.path.insert(0, str(REPO_ROOT / "backend"))

from devon_ai import contracts as c  # noqa: E402
from eval_cases import load_cases  # noqa: E402
from eval_runner import (  # noqa: E402
    ExecutionError,
    rejudge_cases,
    run_cases,
    validate_rejudge_source,
)

from app.core.config import Settings, get_settings  # noqa: E402
from app.integrations.llm.client import CallBudget, call_model  # noqa: E402
from scripts.ai_eval_bridge import ServiceExecutor, prepare  # noqa: E402
from scripts.ai_model_judge import ModelJudge  # noqa: E402


class ModelAttemptBudget:
    """작업별 2회 상한과 별개로 평가 실행 전체의 최대 HTTP 시도를 제한한다."""

    def __init__(self, maximum: int, settings: Any, *, http_client: Any = None) -> None:
        if type(maximum) is not int or maximum < 1:
            raise ValueError("max-model-attempts must be positive")
        self.remaining = maximum
        self.settings, self.http_client = settings, http_client

    def factory(self) -> Any:
        task_budget = CallBudget()

        async def invoke(request: c.ModelRequest, validator: Any) -> Any:
            # 첫 await 전에 예약하여 병렬 report task도 같은 잔여 예산을 중복 사용하지 않는다.
            reserved = min(self.remaining, request.max_attempts, task_budget.remaining_attempts)
            if reserved <= 0:
                return c.ModelResult(
                    None,
                    c.CallFailure(
                        "budget", "evaluation_budget_exhausted", "Evaluation attempt limit reached."
                    ),
                    (),
                )
            self.remaining -= reserved
            result = await call_model(
                replace(request, max_attempts=reserved),
                validator,
                api_key=self.settings.openai_api_key,
                base_url=self.settings.llm_base_url,
                budget=task_budget,
                http_client=self.http_client,
            )
            self.remaining += reserved - len(result.attempts)
            return result

        return invoke


def load_manifest(path: Path) -> tuple[dict[str, c.PromptSpec], c.CallLimits, dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    if (
        type(raw) is not dict
        or not {"prompts", "limits"} <= set(raw) <= {"prompts", "limits", "task_limits"}
        or type(raw["prompts"]) is not list
    ):
        raise ValueError("manifest needs prompts and limits")
    prompts, versions = {}, []
    for entry in raw["prompts"]:
        if type(entry) is not dict or set(entry) != {
            "task_name",
            "version",
            "model",
            "template_path",
        }:
            raise ValueError("invalid prompt manifest entry")
        template_path = (path.parent / entry["template_path"]).resolve()
        template = template_path.read_text(encoding="utf-8-sig")
        prompt = c.PromptSpec(entry["task_name"], entry["version"], entry["model"], template)
        if prompt.task_name in prompts:
            raise ValueError("duplicate prompt task")
        prompts[prompt.task_name] = prompt
        versions.append(
            {key: entry[key] for key in ("task_name", "version", "model")}
            | {
                "template_sha256": hashlib.sha256(template.encode("utf-8")).hexdigest(),
            }
        )
    limits = c.CallLimits(**raw["limits"])
    overrides = raw.get("task_limits", {})
    if type(overrides) is not dict:
        raise ValueError("task_limits must be a task mapping")
    allowed_fields = {field.name for field in fields(c.CallLimits)}
    for task, values in overrides.items():
        if (
            type(task) is not str
            or not task.strip()
            or type(values) is not dict
            or set(values) - allowed_fields
        ):
            raise ValueError("invalid task_limits override")
        replace(limits, **values)
    return prompts, limits, {"prompts": versions, "limits": raw["limits"], "task_limits": overrides}


def source_metadata() -> dict[str, Any]:
    try:
        revision = (
            subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=REPO_ROOT,
                check=True,
                text=True,
                capture_output=True,
                timeout=5,
            ).stdout.strip()
            or None
        )
    except (OSError, subprocess.SubprocessError):
        # 컨테이너·소스 배포본에는 Git이 없을 수 있다. 원문 오류 대신 한계만 남긴다.
        revision = None
    files = sorted(
        {
            path
            for base in ("ai/src", "ai/evals", "ai/prompts", "backend/app", "backend/scripts")
            for path in (REPO_ROOT / base).rglob("*")
            if path.suffix in {".py", ".md"}
        }
    )
    digests = {
        path.relative_to(REPO_ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in files
    }
    return {
        "source_revision": revision,
        "source_revision_status": "available" if revision else "unavailable",
        "source_revision_error": None if revision else "git_unavailable",
        "source_files": digests,
        "working_source_sha256": hashlib.sha256(
            json.dumps(digests, sort_keys=True).encode()
        ).hexdigest(),
    }


def dataset_metadata(root: Path) -> dict[str, Any]:
    """입력·정답·새 합성 전제의 버전을 남기며 절대 경로나 원문을 복제하지 않는다."""
    files = [
        path for folder in ("inputs", "expectations") for path in (root / folder).glob("*.json")
    ]
    binding = root / "binding-manifest.json"
    if binding.is_file():
        files.append(binding)
    digests = {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(files)
    }
    return {
        "files": digests,
        "sha256": hashlib.sha256(json.dumps(digests, sort_keys=True).encode()).hexdigest(),
    }


def _bindings(cases: list[Any]) -> dict[str, dict[str, object]]:
    bindings: dict[str, dict[str, object]] = {}
    for case in cases:
        stem = f"{case.case_id}.v{case.version}"
        try:
            task, _ = prepare(case.kind, case.model_input())
            bindings[stem] = {"status": "valid", "service_task": task}
        except ExecutionError as error:
            bindings[stem] = {
                "status": "invalid",
                "error_stage": error.stage,
                "error_code": error.code,
            }
        except Exception as error:
            bindings[stem] = {
                "status": "invalid",
                "error_stage": "input",
                "error_code": type(error).__name__,
            }
    return bindings


async def execute(args: argparse.Namespace) -> dict[str, Any]:
    llm_judge = getattr(args, "llm_judge", False)
    calibration_only = getattr(args, "calibrate_judge_only", False)
    judge_maximum = getattr(args, "max_judge_attempts", None)
    diagnostic_judge = getattr(args, "diagnostic_judge", False)
    rejudge_path = getattr(args, "rejudge_results", None)
    judge_prompt_version = getattr(args, "judge_prompt_version", None)
    if judge_prompt_version is not None and (
        not llm_judge
        or getattr(args, "judge_prompt", None) is None
        or type(judge_prompt_version) is not str
        or not 1 <= len(judge_prompt_version) <= 100
        or any(not (char.isalnum() or char in "_.@-") for char in judge_prompt_version)
    ):
        raise ValueError("explicit Judge prompt version requires a bounded custom Judge prompt")
    if rejudge_path is not None and (
        args.execute or calibration_only or not llm_judge or args.max_model_attempts is not None
    ):
        raise ValueError(
            "--rejudge-results requires only bounded --llm-judge, no service execution"
        )
    if diagnostic_judge and (not args.execute or not (llm_judge or args.grader)):
        raise ValueError("--diagnostic-judge requires explicit --execute and a grader")
    if calibration_only and not llm_judge:
        raise ValueError("--calibrate-judge-only requires --llm-judge")
    if llm_judge and not (args.execute or calibration_only or rejudge_path is not None):
        raise ValueError("--llm-judge requires explicit execution or calibration-only mode")
    if llm_judge and (type(judge_maximum) is not int or judge_maximum < 1):
        raise ValueError("--llm-judge requires positive --max-judge-attempts")
    if not llm_judge and judge_maximum is not None:
        raise ValueError("--max-judge-attempts requires --llm-judge")
    if args.grader and llm_judge:
        raise ValueError("--grader and --llm-judge are mutually exclusive")
    if args.execute and (type(args.max_model_attempts) is not int or args.max_model_attempts < 1):
        raise ValueError("--execute requires positive --max-model-attempts")
    if args.grader and not args.execute:
        raise ValueError("validation mode does not execute a grader")
