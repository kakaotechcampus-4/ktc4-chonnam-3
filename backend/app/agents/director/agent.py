"""검증된 기존 질문 생성과 신규 Director 실행을 BE 호출 설정에 연결한다."""

from collections.abc import Mapping
from dataclasses import replace
from functools import partial

import httpx
from devon_ai import contracts as c
from devon_ai.agents.director import agent as director
from devon_ai.agents.director.runtime import DirectorOutcome

from app.core.config import LLMSettings
from app.integrations.llm.client import CallBudget, call_model


async def generate_question(
    context: c.Context,
    question_contract: c.QuestionContract,
    *,
    prompt: c.PromptSpec,
    review: director.QuestionReviewer,
    settings: LLMSettings,
    budget: CallBudget,
    answer_analysis: c.ContractChecked[c.AnswerAnalysis] | None = None,
    reference_texts: Mapping[c.BasisRef, str] | None = None,
    http_client: httpx.AsyncClient | None = None,
    attempt_sink: list[c.AttemptMetadata] | None = None,
) -> c.ModelResult[c.ContractChecked[c.Question]]:
    """공유 예산으로 생성하고 검토 취소·예외 전에도 완료된 호출 기록을 보존한다."""
    model_call = partial(
        call_model,
        api_key=settings.openai_api_key,
        base_url=settings.llm_base_url,
        budget=budget,
        http_client=http_client,
        attempt_sink=attempt_sink,
    )
    return await director.generate_question(
        context,
        question_contract,
        prompt=prompt,
        limits=settings.call_limits(),
        model_call=model_call,
        review=review,
        answer_analysis=answer_analysis,
        reference_texts=reference_texts,
    )


async def execute_director(
    context: c.Context,
    *,
    prompt: c.PromptSpec,
    settings: LLMSettings,
    budget: CallBudget,
    answer_analysis: c.ContractChecked[c.AnswerAnalysis] | None = None,
    reference_texts: Mapping[c.BasisRef, str] | None = None,
    prior_analyses: Mapping[str, c.ContractChecked[c.AnswerAnalysis]] | None = None,
    tool_results: tuple[c.ToolResult, ...] = (),
    http_client: httpx.AsyncClient | None = None,
    attempt_sink: list[c.AttemptMetadata] | None = None,
) -> c.ModelResult[DirectorOutcome]:
    """같은 두 시도 예산으로 목적·초안 생성과 독립 검토를 연결한다."""
    from devon_ai.agents.director import runtime

    failure = budget.terminal_failure
    if failure is not None:
        return c.ModelResult(None, failure, ())
    remaining = min(context.limits.remaining_calls, budget.remaining_attempts)
    if remaining < 2:
        return c.ModelResult(
            None,
            c.CallFailure("budget", "llm_failed", "Generation and review require two attempts."),
            (),
        )
    # Context는 허용량 스냅샷이다. 실제 예산을 소유한 BE에서만 잔여량을 맞춘다.
    context = replace(context, limits=replace(context.limits, remaining_calls=remaining))
    return await runtime.run_director(
        context,
        prompt=prompt,
        limits=settings.call_limits(),
        model_call=partial(
            call_model,
            api_key=settings.openai_api_key,
            base_url=settings.llm_base_url,
            budget=budget,
            http_client=http_client,
            attempt_sink=attempt_sink,
        ),
        answer_analysis=answer_analysis,
        reference_texts=reference_texts,
        prior_analyses=prior_analyses,
        tool_results=tool_results,
    )
