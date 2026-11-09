"""도메인 판정은 회사명 대신 실제 직무 원문과 검증된 문단을 사용한다."""

import json

import httpx
from devon_ai import contracts as c

from app.core.config import LLMSettings


async def test_domain_wrapper_keeps_original_paragraph_and_does_not_send_company():
    from app.llm_tasks.domain_category import classify_posting_domain

    sent = []

    def handler(request):
        body = json.loads(request.content)
        payload = json.loads(body["input"][0]["content"][0]["text"])
        sent.append(payload)
        return httpx.Response(
            200,
            json={
                "id": "fixture",
                "model": "fixture",
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "status": "completed",
                        "content": [
                            {
                                "type": "output_text",
                                "text": json.dumps(
                                    {"category": "shopping", "evidence_id": "main_tasks:0"}
                                ),
                            }
                        ],
                    }
                ],
                "usage": {"input_tokens": 5, "output_tokens": 5},
            },
        )

    settings = LLMSettings(
        openai_api_key="fixture",
        llm_default_model="fixture",
        llm_timeout_seconds=1,
        llm_max_input_bytes=10000,
        llm_max_output_tokens=512,
        llm_max_response_bytes=10000,
    )
    posting = c.DomainPostingInput("Engineer", None, (" 주문 서비스를 개발합니다. ",), (), ())
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await classify_posting_domain(
            posting,
            prompt=c.PromptSpec("domain_category", "domain_category_v2", "fixture", "fixture"),
            settings=settings,
            http_client=client,
        )
    assert result.category == "shopping"
    assert result.evidence == " 주문 서비스를 개발합니다. "
    assert set(sent[0]) == {"position", "intro", "main_tasks", "requirements", "preferred_points"}
    assert result.failure is None
