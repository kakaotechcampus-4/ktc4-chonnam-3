"""검수된 UTF-8 프롬프트 파일을 현재 설정 모델의 명시적 버전으로 등록한다."""

import argparse
import asyncio
import sys
from pathlib import Path

from devon_ai.contracts import PromptSpec
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from scripts.seed_prompt_versions import PROMPT_VERSIONS, register_prompt_versions


async def register(task: str, version: str, template: Path) -> PromptSpec:
    settings = get_settings()
    model = settings.require_llm().llm_default_model
    body = await asyncio.to_thread(template.read_text, encoding="utf-8")
    prompt = PromptSpec(task, version, model, body)
    engine = create_async_engine(settings.database_url)
    try:
        # 등록과 활성 전환을 함께 확정하고 충돌이나 DB 오류는 함께 되돌린다.
        async with async_sessionmaker(engine).begin() as session:
            await register_prompt_versions(session, (prompt,))
    finally:
        await engine.dispose()
    return prompt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", required=True, choices=tuple(PROMPT_VERSIONS))
    parser.add_argument("--version", required=True)
    parser.add_argument("--template", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        prompt = asyncio.run(register(args.task, args.version, args.template))
    except Exception:
        # 파일·설정·DB 예외에 포함될 수 있는 비밀값과 원문을 표준 오류에 내보내지 않는다.
        print(
            "Prompt registration failed. Check the file, configuration, and database.",
            file=sys.stderr,
        )
        return 1
    print(f"task={prompt.task_name} version={prompt.version} model={prompt.model}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
