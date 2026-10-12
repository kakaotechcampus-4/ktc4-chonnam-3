"""L2 저장소 정밀 분석의 BE 연결 계층.

분석·notable area 검증은 ``devon_ai.llm_tasks.repo_deep``가 맡는다. 이 모듈은 공급자 호출을
준비하고 결과를 repo_analyses 행 값으로 바꾼다. primary 선정·고정 ref 원문 조회·prompt 조회와
DB 저장·캐시 조회는 service(pipeline deep_analysis)가 소유한다. 이 모듈은 DB session을 받지 않는다.
"""

import uuid
from functools import partial

import httpx
from devon_ai import contracts as c
from devon_ai.llm_tasks.repo_deep import analyze_deep

from app.core.config import LLMSettings
from app.integrations.llm.client import CallBudget, call_model
from app.llm_tasks.repo_shallow import _call_record

type DeepResult = c.ModelResult[c.ContractChecked[c.DeepAnalysisResult]]

# docs/error-reasons.md 의 repo_analyses.error_code 중 LLM 단계 값
_LLM_ERROR_CODES = frozenset({"llm_timeout", "llm_parse_failed", "llm_failed"})


async def analyze_repository(
    item: c.DeepRepoInput,
    *,
    snapshot_head_sha: str,
    prompt: c.PromptSpec,
    settings: LLMSettings,
    http_client: httpx.AsyncClient,
) -> DeepResult:
    """저장소 하나의 L2 작업에 CallBudget 하나를 묶어 총 2회 호출로 제한한다.

    snapshot_head_sha는 session_repositories의 고정 ref다. prompt는 service가 호출 전에 읽는다.
    """

    model_call = partial(
        call_model,
        api_key=settings.openai_api_key,
        http_client=http_client,
        budget=CallBudget(),
    )
    return await analyze_deep(
        item,
        snapshot_head_sha=snapshot_head_sha,
        prompt=prompt,
        limits=settings.call_limits(),
        model_call=model_call,
    )


def to_repo_analysis_row(
    result: DeepResult, item: c.DeepRepoInput, prompt: c.PromptSpec
) -> dict[str, object]:
    """repo_analyses 행 값. 검증된 notable area가 없으면 실패이며 기본 관찰을 채우지 않는다.

    거절한 area는 result의 rejected_areas에 남겨 내부 context limitations의 출처로 쓴다.
    """
    attempt = result.attempts[-1] if result.attempts else None
    row: dict[str, object] = {
        **_call_record(attempt, prompt),
        "repository_id": uuid.UUID(item.repository_id),
        "analysis_level": "l2",
        "head_sha": item.head_sha,
        "prompt_version": prompt.version,
        "batch_position": None,
        # L2 요약의 저장 필드는 BE 합의 전이다. architecture_summary는 result에만 둔다.
        "summary": None,
    }
    if result.data is None:
        failure = result.failure
        code = failure.error_code if failure is not None else "llm_failed"
        code = code if code in _LLM_ERROR_CODES else "llm_failed"
        # 요청을 보내기 전 크기 상한으로 거절되면 시도 기록이 없다. 응답 초과는 시도가 남는다.
        if failure is not None and failure.stage == "budget" and not result.attempts:
            code = "input_too_large"
        return row | {
            "status": "failed",
            "error_code": code,
            "tech_stack": [],
            "notable_areas": None,
            "result": None,
        }
    data = c.to_data(result.data)
    analysis = result.data.data.analysis
    if analysis is None:
        # 모든 area가 거절되면 semantic 실패다. 거절 사유는 result에 보존한다.
        return row | {
            "status": "failed",
            "error_code": "llm_failed",
            "tech_stack": [],
            "notable_areas": None,
            "result": data,
        }
    stored = data["analysis"]
    assert isinstance(stored, dict)
    return row | {
        "status": "succeeded",
        "error_code": None,
        "tech_stack": list(analysis.confirmed_technologies),
        "notable_areas": stored["notable_areas"],
        "result": data,
    }


__all__ = ["analyze_repository", "to_repo_analysis_row"]
