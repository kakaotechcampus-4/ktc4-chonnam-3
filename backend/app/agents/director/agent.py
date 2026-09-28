"""검증된 계약 입력과 BE 호출 설정을 AI Director에 연결한다."""

from collections.abc import Mapping
from functools import partial

import httpx
from devon_ai import contracts as c
from devon_ai.agents.director import agent as director

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
