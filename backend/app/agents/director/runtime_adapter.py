"""신규 Director 실행을 실제 BE 호출 예산과 공급자 설정에 연결한다."""

from collections.abc import Callable, Mapping
from dataclasses import replace

import httpx
from devon_ai import contracts as c
from devon_ai.agents.director.runtime import DirectorOutcome, RecoveryFeedback

from app.core.config import LLMSettings
from app.integrations.execution_ledger import observe_call
from app.integrations.llm.client import CallBudget, call_model


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
    recovery_feedback: RecoveryFeedback | None = None,
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

    async def model_call[T](
        request: c.ModelRequest, validator: Callable[[object], T]
    ) -> c.ModelResult[T]:
        operation = request.payload.get("operation")
        stage = "director." + str(operation) if operation in {"plan", "review"} else "director.call"
        async with observe_call(stage, kind="stage") as observed:
            result = await call_model(
                request,
                validator,
                api_key=settings.openai_api_key,
                base_url=settings.llm_base_url,
                budget=budget,
                http_client=http_client,
                attempt_sink=attempt_sink,
            )
            if observed is not None:
                observed.complete(result.failure.error_code if result.failure else None)
            return result

    return await runtime.run_director(
        context,
        prompt=prompt,
        limits=settings.call_limits(prompt.task_name),
        model_call=model_call,
        answer_analysis=answer_analysis,
        reference_texts=reference_texts,
        prior_analyses=prior_analyses,
        tool_results=tool_results,
        recovery_feedback=recovery_feedback,
    )
