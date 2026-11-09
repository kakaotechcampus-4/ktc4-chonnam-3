"""기존 AI Claim 추출을 실제 공급자 호출과 분리된 예산에 연결한다."""

from functools import partial

import httpx
from devon_ai import contracts as c
from devon_ai.llm_tasks.doc_claims import ClaimExtraction, extract_claims

from app.core.config import LLMSettings
from app.integrations.llm.client import CallBudget, call_model


async def analyze_document_claims(
    text: str,
    *,
    prompt: c.PromptSpec,
    settings: LLMSettings,
    http_client: httpx.AsyncClient | None = None,
    attempt_sink: list[c.AttemptMetadata] | None = None,
) -> ClaimExtraction:
    return await extract_claims(
        text,
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
