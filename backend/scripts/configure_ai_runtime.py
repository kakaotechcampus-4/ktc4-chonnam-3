"""설정 모델로 실행·평가용 프롬프트 manifest를 만들고 명시적으로 DB에 등록한다."""

import argparse
import asyncio
import json
import os
import sys
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
from typing import Any

from devon_ai import contracts as c
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import LLMSettings, Settings
from app.llm_tasks.question_pronunciation import QUESTION_PRONUNCIATION_TASK
from app.llm_tasks.runtime_capabilities import validate_runtime_prompts
from scripts.seed_prompt_versions import register_prompt_versions

PROMPT_ROOT = Path(__file__).resolve().parents[2] / "ai" / "prompts"


def build_manifest(
    model: str,
    limits: c.CallLimits,
    output: Path,
    *,
    deployment: str | None = None,
    task_timeouts: dict[str, float] | None = None,
    pronunciation_model: str | None = None,
) -> dict[str, Any]:
    """배포 설정을 구체 모델·본문 경로로 해석한다. API나 DB를 호출하지 않는다."""
    if deployment is not None:
        import re

        if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,47}", deployment) is None:
            raise ValueError("Invalid deployment identity")
    recipe = json.loads((PROMPT_ROOT / "runtime-prompts.json").read_text(encoding="utf-8"))
    prompts = []
    for task, entry in recipe.items():
        task_model, task_deployment = model, deployment
        if task == QUESTION_PRONUNCIATION_TASK:
            task_model = pronunciation_model or model
            # 발음 모델 변경은 이 작업의 불변 프롬프트 버전에만 영향을 준다.
            model_identity = sha256(task_model.encode()).hexdigest()[:16]
            task_deployment = f"{deployment}-{model_identity}" if deployment else model_identity
        template = PROMPT_ROOT / entry["template"]
        body = template.read_text(encoding="utf-8")
        version = entry["version"] + ("@" + task_deployment if task_deployment else "")
        c.PromptSpec(task, version, task_model, body)
        prompts.append(
            dict(
                task_name=task,
                version=version,
                model=task_model,
                template_path=os.path.relpath(template, output.parent).replace("\\", "/"),
            )
        )
    manifest: dict[str, Any] = {"prompts": prompts, "limits": asdict(limits)}
    if task_timeouts:
        if set(task_timeouts) - set(recipe):
            raise ValueError("Timeout configured for an unknown runtime task")
        manifest["task_limits"] = {
            task: {"timeout_seconds": seconds} for task, seconds in task_timeouts.items()
        }
    return manifest


async def apply_manifest(manifest: dict[str, object], output: Path, database_url: str) -> None:
    prompts = []
    entries = manifest["prompts"]
    assert isinstance(entries, list)
    for entry in entries:
        template = (output.parent / entry["template_path"]).resolve().read_text(encoding="utf-8")
        prompts.append(c.PromptSpec(entry["task_name"], entry["version"], entry["model"], template))
    # 소비자 전체가 준비된 뒤에만 한 트랜잭션으로 활성화한다.
    validate_runtime_prompts(prompts)
    engine = create_async_engine(database_url)
    try:
        async with async_sessionmaker(engine).begin() as db:
            await register_prompt_versions(db, prompts)
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--apply", action="store_true", help="현재 설정 DB에 등록·활성화")
    parser.add_argument("--deployment", help="기존 버전을 보존할 모델 배포 식별자")
    args = parser.parse_args(argv)
    try:
        settings = Settings(_env_file=args.env_file)
        llm = settings.require_llm()
        output = args.output.resolve()
        manifest = build_manifest(
            llm.llm_default_model,
            llm.call_limits(),
            output,
            deployment=args.deployment,
            task_timeouts=llm.llm_task_timeouts,
            pronunciation_model=settings.tts_pronunciation_model,
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        if args.apply:
            asyncio.run(apply_manifest(manifest, output, settings.database_url))
    except ValidationError as error:
        # 입력값·검증 문구에는 비밀값이 섞일 수 있어 알려진 필드명만 출력한다.
        known_fields = set(getattr(Settings, "model_fields", {})) | set(LLMSettings.model_fields)
        fields = sorted(
            {
                str(item["loc"][0])
                for item in error.errors()
                if item["loc"] and item["loc"][0] in known_fields
            }
        )
        print(
            "Runtime configuration failed. Invalid settings fields: "
            + ", ".join(fields or ["unknown"]),
            file=sys.stderr,
        )
        return 1
    except Exception:
        # URL·설정값·키를 포함할 수 있는 원래 예외를 출력하지 않는다.
        print(
            "Runtime configuration failed. Check settings, prompt versions and database.",
            file=sys.stderr,
        )
        return 1
    print(
        json.dumps(
            {
                "mode": "applied" if args.apply else "manifest_only",
                "prompts": len(manifest["prompts"]),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
