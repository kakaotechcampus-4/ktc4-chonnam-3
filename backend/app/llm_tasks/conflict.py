"""문서 Claim 대조를 기존 Model Gateway의 한 배치·최대 두 시도에 연결한다."""

from functools import partial

import httpx
from devon_ai import contracts as c
from devon_ai.llm_tasks.claim_code import ClaimComparisonResult, ClaimForComparison, compare_claims

from app.core.config import LLMSettings
from app.integrations.llm.client import CallBudget, call_model


async def compare_document_claims(
    claims: tuple[ClaimForComparison, ...],
    evidences: tuple[c.Evidence, ...],
    *,
    prompt: c.PromptSpec,
    settings: LLMSettings,
    http_client: httpx.AsyncClient | None = None,
    attempt_sink: list[c.AttemptMetadata] | None = None,
) -> ClaimComparisonResult:
    return await compare_claims(
        claims,
        evidences,
        prompt=prompt,
        limits=settings.call_limits(prompt.task_name),
        model_call=partial(
            call_model,
            api_key=settings.openai_api_key,
            base_url=settings.llm_base_url,
            budget=CallBudget(),
            http_client=http_client,
            attempt_sink=attempt_sink,
        ),
    )
