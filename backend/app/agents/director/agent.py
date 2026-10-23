"""Backend adapter boundary for canonical logic in ``devon_ai.agents.director.agent``.

Backend services retain state, permissions, persistence, and orchestration. This module will
adapt validated service inputs once the AI contract is implemented.
"""

from collections.abc import Mapping
from functools import partial

import httpx
from devon_ai import contracts as c
from devon_ai.agents.director.runtime import DirectorOutcome

from app.core.config import LLMSettings
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
    http_client: httpx.AsyncClient | None = None,
    attempt_sink: list[c.AttemptMetadata] | None = None,
) -> c.ModelResult[DirectorOutcome]:
    """같은 두 시도 예산으로 목적·초안 생성과 독립 검토를 연결한다."""
    from devon_ai.agents.director import runtime

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
