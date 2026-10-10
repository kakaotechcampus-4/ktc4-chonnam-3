""".env의 정상 연결 경로로 합성 저장소 1건을 분석한다. 실제 API 사용량이 발생한다.

backend에서 ``python -m scripts.check_llm``으로 명시적으로 실행한다.
진단용 프롬프트는 DB에 등록하지 않으며 실제 저장소·사용자 자료를 전송하지 않는다.
"""

import asyncio
import json
import logging
from uuid import UUID

import httpx
from devon_ai.contracts import LanguageBytes, PromptSpec, ShallowRepoInput

from app.core.config import get_settings
from app.llm_tasks.repo_shallow import analyze_repositories, to_repo_analysis_rows


async def check_connection() -> dict[str, object]:
    settings = get_settings().require_llm()
    source = ShallowRepoInput(
        repository_id=str(UUID(int=42)),
        head_sha="a" * 40,
        description="Synthetic Python task-list command line application.",
        readme_text=(
            "This synthetic Python command line project adds tasks, lists tasks and marks "
            "tasks complete. Data is saved in a local JSON file. No external service is used. "
            "Runtime and individual contribution have not been verified."
        ),
        readme_truncated=False,
        languages=(LanguageBytes("Python", 1000),),
        commit_count=10,
        user_commit_count=3,
        collection_errors=(),
    )
    # 연결 점검 전용 버전이다. 앱의 활성 프롬프트·팀 기본 모델을 덮어쓰지 않는다.
    prompt = PromptSpec(
        "repo_shallow",
        "l1_connection_check",
        settings.llm_default_model,
        "Analyze only the supplied repository facts. Return the required JSON with one "
        "result per repository. Copy each repository_id and head_sha exactly. Use Korean "
        "prose and literal technology names. Do not invent frameworks or individual "
        "contributions. Include evidence from the provided README and mention that runtime "
        "was not verified. Keep each prose field concise.",
    )
    async with httpx.AsyncClient(follow_redirects=False) as http:
        run = await analyze_repositories(
            (source,), prompt=prompt, settings=settings, http_client=http
        )
    rows = to_repo_analysis_rows(run, (source,), prompt)
    failure = run.result.failure
    return {
        "success": rows[0]["status"] == "succeeded",
        "configured_model": settings.llm_default_model,
        "prompt_version": prompt.version,
        "synthetic_input_only": True,
        "database_written": False,
        "succeeded_items": sum(row["status"] == "succeeded" for row in rows),
        "failed_items": sum(row["status"] == "failed" for row in rows),
        # HTTP 성공 뒤 항목 검증 실패와 전송 전 예산 거절도 provider 시도와 별도로 남긴다.
        "batch_failure": (
            {"stage": failure.stage, "error_code": failure.error_code} if failure else None
        ),
        "item_failures": (
            [{"stage": item.stage} for item in run.result.data.data.failed]
            if run.result.data is not None
            else []
        ),
        "attempts": [
            {
                "model": attempt.model,
                "latency_ms": attempt.latency_ms,
                "input_tokens": attempt.input_tokens,
                "output_tokens": attempt.output_tokens,
                "error_stage": attempt.error_stage,
                "error_code": attempt.error_code,
            }
            for _, call in run.calls
            for attempt in call.attempts
        ],
    }


def main() -> int:
    # 독립 점검 명령의 HTTP 로그에 프록시 namespace나 토큰을 남기지 않는다.
    logging.getLogger("httpx").setLevel(logging.CRITICAL)
    logging.getLogger("httpcore").setLevel(logging.CRITICAL)
    try:
        result = asyncio.run(check_connection())
    except Exception:
        print("LLM 연결 점검 실패: 환경 설정과 설치 상태를 확인하세요.")
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
