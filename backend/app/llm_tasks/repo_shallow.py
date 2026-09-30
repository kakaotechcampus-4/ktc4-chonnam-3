"""L1 저장소 기본 분석의 BE 연결 계층.

분석·검증·재요청은 ``devon_ai.llm_tasks.repo_shallow``가 맡는다. 이 모듈은 공급자 호출을
준비하고 결과를 repo_analyses 행 값으로 바꾼다. prompt 조회와 DB 저장·캐시 조회·run 집계는
service(pipeline repo_analyze)가 소유한다. 이 모듈은 DB session을 받지 않는다.
"""

import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import partial
from typing import cast

import httpx
from devon_ai import contracts as c
from devon_ai.llm_tasks.repo_shallow import analyze_shallow_batch

from app.core.config import LLMSettings
from app.integrations.llm.client import CallBudget, call_model

type ShallowChecked = c.ContractChecked[c.ShallowBatchResult]
type ShallowResult = c.ModelResult[ShallowChecked]

# docs/error-reasons.md 의 repo_analyses.error_code 중 LLM 단계 값
_LLM_ERROR_CODES = frozenset({"llm_timeout", "llm_parse_failed", "llm_failed"})


@dataclass(frozen=True)
class ShallowRun:
    """최종 결과와 호출별 (요청 저장소 ID, 결과). 행의 호출 기록 출처를 원문 재해석 없이 정한다."""

    result: ShallowResult
    calls: tuple[tuple[frozenset[str], ShallowResult], ...]


async def analyze_repositories(
    inputs: tuple[c.ShallowRepoInput, ...],
    *,
    prompt: c.PromptSpec,
    settings: LLMSettings,
    http_client: httpx.AsyncClient,
) -> ShallowRun:
    """한 논리 작업에 CallBudget 하나를 묶어 부분 재요청까지 총 2회 호출로 제한한다.

    prompt는 호출 전에 service가 load_active_prompt로 읽고 조회 transaction을 끝낸 뒤 넘긴다.
    """
    model_call = partial(
        call_model,
        api_key=settings.openai_api_key,
        http_client=http_client,
        budget=CallBudget(),
    )
    calls: list[tuple[frozenset[str], ShallowResult]] = []

    async def recorded(
        request: c.ModelRequest, validator: Callable[[object], ShallowChecked]
    ) -> ShallowResult:
        requested = cast(list[dict[str, str]], request.payload["repositories"])
        out = await model_call(request, validator)
        calls.append((frozenset(item["repository_id"] for item in requested), out))
        return out

    result = await analyze_shallow_batch(
        inputs, prompt=prompt, limits=settings.call_limits(), model_call=recorded
    )
    return ShallowRun(result, tuple(calls))


def to_repo_analysis_rows(
    run: ShallowRun, inputs: Sequence[c.ShallowRepoInput], prompt: c.PromptSpec
) -> list[dict[str, object]]:
    """입력 저장소마다 repo_analyses 행 값을 만든다. 실패 행에 요약·기술 기본값을 채우지 않는다.

    status는 succeeded/failed만 만든다. 부분 수집 등에 따른 partial 판정은 service 책임이다.
    """
    # ponytail: 배치 호출 기록이라 저장소별 token·latency를 나눌 수 없어 그 저장소 결과를 만든
    # 시도의 배치 값을 넣는다(batch_position으로 구분). 저장소별 비용이 필요하면 별도 집계로 옮긴다.
    result = run.result
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

    rows: list[dict[str, object]] = []
    for position, item in enumerate(inputs):
        found = analyses.get(item.repository_id)
        row = {
            **base,
            **_call_record(_deciding_attempt(run, item.repository_id), prompt),
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


def _deciding_attempt(run: ShallowRun, repository_id: str) -> c.AttemptMetadata | None:
    """이 저장소 결과를 정한 시도. 호출 전체 실패면 마지막 실패 시도다.

    그 외에는 이 저장소를 요청했고 검증 결과를 돌려준 마지막 호출의 성공 시도다. 재요청이 통째로
    실패하면 첫 결과가 유지되므로 첫 호출의 성공 시도가 된다.
    """
    if run.result.data is None:
        return run.result.attempts[-1] if run.result.attempts else None
    for requested, call in reversed(run.calls):
        if call.data is not None and repository_id in requested:
            return call.attempts[-1]
    return None


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


__all__ = ["ShallowRun", "analyze_repositories", "to_repo_analysis_rows"]
