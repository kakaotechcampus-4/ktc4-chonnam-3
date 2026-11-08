"""Backend adapter boundary for ``devon_ai.llm_tasks.answer_analysis``.

The canonical AI module will own answer-analysis logic. The backend retains prompt loading,
provider I/O, interview-state checks, and persistence responsibilities.
"""

from collections.abc import Callable
from dataclasses import replace

import httpx
from devon_ai import contracts as c
from devon_ai.llm_tasks.answer_analysis import analyze_answer as analyze

from app.core.config import LLMSettings
from app.integrations.llm.client import CallBudget, call_model


async def analyze_answer(
    context: c.Context,
    question: c.ContractChecked[c.Question],
    *,
    turn_id: str,
    answer_text: str,
    prompt: c.PromptSpec,
    settings: LLMSettings,
    budget: CallBudget,
    tool_results: tuple[c.ToolResult, ...] = (),
    allowed_locations: frozenset[tuple[str, str, str]] = frozenset(),
    max_attempts: int = 2,
    http_client: httpx.AsyncClient | None = None,
    attempt_sink: list[c.AttemptMetadata] | None = None,
) -> c.ModelResult[c.ContractChecked[c.AnswerAnalysis]]:
    """도구 보강 전후에도 동일한 T3 예산과 완료 시도 기록을 사용한다."""

    async def model_call(
        request: c.ModelRequest,
        validate: Callable[[object], c.ContractChecked[c.AnswerAnalysis]],
    ) -> c.ModelResult[c.ContractChecked[c.AnswerAnalysis]]:
        return await call_model(
            replace(request, max_attempts=min(max_attempts, request.max_attempts)),
            validate,
            api_key=settings.openai_api_key,
            base_url=settings.llm_base_url,
            budget=budget,
            http_client=http_client,
            attempt_sink=attempt_sink,
        )

    return await analyze(
        context,
        question,
        turn_id=turn_id,
        answer_text=answer_text,
        prompt=prompt,
        limits=settings.call_limits(),
        model_call=model_call,
        tool_results=tool_results,
        allowed_locations=allowed_locations,
    )
