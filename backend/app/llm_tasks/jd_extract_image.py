"""실제 설정과 두 시도 예산으로 이미지 JD 전사 분류를 호출한다."""

from collections.abc import Mapping
from functools import partial

import httpx
from devon_ai import contracts as c
from devon_ai.llm_tasks.jd_extract_image import ImageJdResult, extract_image_requirements

from app.core.config import LLMSettings
from app.integrations.llm.client import CallBudget, call_model


async def analyze_image_requirements(
    blocks: Mapping[str, str],
    *,
    prompt: c.PromptSpec,
    settings: LLMSettings,
    http_client: httpx.AsyncClient | None,
    max_requirements: int,
) -> c.ModelResult[ImageJdResult]:
    return await extract_image_requirements(
        blocks,
        prompt=prompt,
        limits=settings.call_limits(prompt.task_name),
        max_requirements=max_requirements,
        model_call=partial(
            call_model,
            api_key=settings.openai_api_key,
            base_url=settings.llm_base_url,
            http_client=http_client,
            budget=CallBudget(),
        ),
    )
