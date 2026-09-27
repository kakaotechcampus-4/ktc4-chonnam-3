"""L1 저장소 기본 분석의 BE 연결 계층.

분석·검증·재요청은 ``devon_ai.llm_tasks.repo_shallow``가 맡는다. 이 모듈은 공급자 호출을
준비하고 결과를 repo_analyses 행 값으로 바꾼다. prompt 조회와 DB 저장·캐시 조회·run 집계는
service(pipeline repo_analyze)가 소유한다. 이 모듈은 DB session을 받지 않는다.
"""

import json
import uuid
from collections.abc import Sequence
from functools import partial
from typing import cast

import httpx
from devon_ai import contracts as c
from devon_ai.llm_tasks.repo_shallow import analyze_shallow_batch

from app.core.config import LLMSettings
from app.integrations.llm.client import CallBudget, call_model

type ShallowResult = c.ModelResult[c.ContractChecked[c.ShallowBatchResult]]

# docs/error-reasons.md 의 repo_analyses.error_code 중 LLM 단계 값
_LLM_ERROR_CODES = frozenset({"llm_timeout", "llm_parse_failed", "llm_failed"})


async def analyze_repositories(
    inputs: tuple[c.ShallowRepoInput, ...],
    *,
    prompt: c.PromptSpec,
    settings: LLMSettings,
    http_client: httpx.AsyncClient,
) -> ShallowResult:
    """한 논리 작업에 CallBudget 하나를 묶어 부분 재요청까지 총 2회 호출로 제한한다.

    prompt는 호출 전에 service가 load_active_prompt로 읽고 조회 transaction을 끝낸 뒤 넘긴다.
    """
    model_call = partial(
        call_model,
        api_key=settings.openai_api_key,
        http_client=http_client,
        budget=CallBudget(),
    )
    return await analyze_shallow_batch(
        inputs, prompt=prompt, limits=settings.call_limits(), model_call=model_call
    )


def to_repo_analysis_rows(
    result: ShallowResult, inputs: Sequence[c.ShallowRepoInput], prompt: c.PromptSpec
) -> list[dict[str, object]]:
    """입력 저장소마다 repo_analyses 행 값을 만든다. 실패 행에 요약·기술 기본값을 채우지 않는다.

    status는 succeeded/failed만 만든다. 부분 수집 등에 따른 partial 판정은 service 책임이다.
    """
    # ponytail: 배치 호출 기록이라 저장소별 token·latency를 나눌 수 없어 그 저장소 결과를 만든
    # 시도의 배치 값을 넣는다(batch_position으로 구분). 저장소별 비용이 필요하면 별도 집계로 옮긴다.
    base: dict[str, object] = {
        "analysis_level": "l1",
        "prompt_version": prompt.version,
        "notable_areas": None,
    }

    analyses: dict[str, tuple[c.ShallowRepoAnalysis, dict[str, object]]] = {}
    failures: dict[str, str] = {}
    if result.data is None:
        call_failure = result.failure
        code = call_failure.error_code if call_failure is not None else "llm_failed"
        whole = code if code in _LLM_ERROR_CODES else "llm_failed"
        # 요청을 보내기 전 크기 상한으로 거절되면 시도 기록이 없다. 응답 초과는 시도가 남는다.
        if call_failure is not None and call_failure.stage == "budget" and not result.attempts:
            whole = "input_too_large"
        failures = {item.repository_id: whole for item in inputs}
    else:
        batch = result.data.data
        stored = cast(list[dict[str, object]], c.to_data(result.data)["succeeded"])
        for analysis, data in zip(batch.succeeded, stored, strict=True):
            analyses[analysis.repository_id] = (analysis, data)
        for failure in batch.failed:
            if failure.repository_id is not None:
                failures.setdefault(
                    failure.repository_id,
                    "llm_parse_failed" if failure.stage == "parse" else "llm_failed",
                )

    # 원문에 한 번도 나오지 않은 저장소는 재요청 대상이 아니므로 첫 호출이 결정했다.
    # 첫 호출은 성공 시도로 끝나며, 호출 전체가 실패했다면 마지막 시도가 끝이다.
    first_call_end = (
        next((a for a in result.attempts if a.error_stage is None), None)
        if result.data is not None
        else None
    ) or (result.attempts[-1] if result.attempts else None)

    rows: list[dict[str, object]] = []
    for position, item in enumerate(inputs):
        found = analyses.get(item.repository_id)
        source = (
            _producing_attempt(result.attempts, found[1])
            if found is not None
            else _failing_attempt(result.attempts, item.repository_id, first_call_end)
        )
        row = {
            **base,
            **_call_record(source, prompt),
            "repository_id": uuid.UUID(item.repository_id),
            "head_sha": item.head_sha,
            "batch_position": position,
        }
        if found is not None:
            analysis, data = found
            # 프로젝트 요약의 저장 필드는 BE 합의 전이다(ADR 0006, spec/ai/contracts.md).
            # 합의 전에는 summary를 비우고 result에만 둔다. 개인 role_summary로는 쓰지 않는다.
            row |= {
                "status": "succeeded",
                "error_code": None,
                "summary": None,
                "tech_stack": list(analysis.tech_stack),
                "result": data,
            }
        else:
            row |= {
                "status": "failed",
                "error_code": failures.get(item.repository_id, "llm_failed"),
                "summary": None,
                "tech_stack": [],
                "result": None,
            }
        rows.append(row)
    return rows


def _call_record(attempt: c.AttemptMetadata | None, prompt: c.PromptSpec) -> dict[str, object]:
    """행에 남길 호출 기록. 호출이 없었으면 설정 모델과 시도 0을 남긴다."""
    if attempt is None:
        return {
            "model": prompt.model,
            "raw_output": None,
            "input_tokens": None,
            "output_tokens": None,
            "latency_ms": None,
            "attempt": 0,
        }
    return {
        "model": attempt.model,
        "raw_output": attempt.raw_output,
        "input_tokens": attempt.input_tokens,
        "output_tokens": attempt.output_tokens,
        "latency_ms": attempt.latency_ms,
        "attempt": attempt.attempt,
    }


def _batch_items(attempt: c.AttemptMetadata) -> list[object]:
    """시도 원문의 repositories 목록. JSON이 아니거나 모양이 다르면 빈 목록이다."""
    if attempt.raw_output is None:
        return []
    try:
        items = json.loads(attempt.raw_output)["repositories"]
    except (ValueError, TypeError, KeyError):
        return []
    return items if isinstance(items, list) else []


def _producing_attempt(
    attempts: Sequence[c.AttemptMetadata], stored: dict[str, object]
) -> c.AttemptMetadata | None:
    """검증된 결과와 같은 항목을 처음 출력한 성공 시도를 찾는다. 재요청 응답과 섞이지 않게 한다."""
    for attempt in attempts:
        if attempt.error_stage is None and stored in _batch_items(attempt):
            return attempt
    return attempts[-1] if attempts else None


def _failing_attempt(
    attempts: Sequence[c.AttemptMetadata],
    repository_id: str,
    fallback: c.AttemptMetadata | None,
) -> c.AttemptMetadata | None:
    """이 저장소를 마지막으로 다룬 시도를 찾는다. 원문에 없으면 fallback(첫 호출의 끝)이다."""
    for attempt in reversed(attempts):
        items = _batch_items(attempt)
        if any(isinstance(i, dict) and i.get("repository_id") == repository_id for i in items):
            return attempt
    return fallback


__all__ = ["analyze_repositories", "to_repo_analysis_rows"]
