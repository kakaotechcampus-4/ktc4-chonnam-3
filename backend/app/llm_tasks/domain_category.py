"""주입된 모델 설정으로 공고 도메인을 판정한다. DB·공고 수집은 호출자가 맡는다."""

from functools import partial

import httpx
from devon_ai import contracts as c
from devon_ai.llm_tasks.domain_category import DomainDecision, classify_domain

from app.core.config import LLMSettings
from app.integrations.llm.client import CallBudget, call_model


async def classify_posting_domain(
    posting: c.DomainPostingInput,
    *,
    prompt: c.PromptSpec,
    settings: LLMSettings,
    http_client: httpx.AsyncClient,
) -> DomainDecision:
    return await classify_domain(
        posting,
        prompt=prompt,
        limits=settings.call_limits(prompt.task_name),
        model_call=partial(
            call_model,
            api_key=settings.openai_api_key,
            base_url=settings.llm_base_url,
            http_client=http_client,
            budget=CallBudget(),
        ),
    )
