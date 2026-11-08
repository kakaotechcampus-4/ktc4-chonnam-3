"""공고 원문·캐시와 도메인 판정 상태를 함께 보존한다."""

import json

import httpx
from sqlalchemy import select

from app.core.config import Settings
from app.db.models import JobPosting, PromptVersion


async def test_saved_posting_domain_uses_one_model_call_and_reuses_verified_result(session_factory):
    from app.features.analysis.posting_domain import classify_saved_posting

    async with session_factory.begin() as db:
        row = JobPosting(
            source="wanted",
            normalized_url="https://www.wanted.co.kr/wd/999",
            raw_url="https://www.wanted.co.kr/wd/999",
            parse_status="succeeded",
            raw_payload={
                "position": "Engineer",
                "company_name": "ignored",
                "industry": "ignored",
                "main_tasks": ["Payments service"],
                "requirements": [],
                "preferred_points": [],
            },
        )
        db.add(row)
        db.add(
            PromptVersion(
                task_name="domain_category",
                version="domain_category_v2",
                model="fixture",
                template="fixture",
                is_active=True,
            )
        )
        await db.flush()
        posting_id = row.id
    calls = []

    def handler(request):
        calls.append(request)
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
                                    {"category": "finance", "evidence_id": "main_tasks:0"}
                                ),
                            }
                        ],
                    }
                ],
                "usage": {"input_tokens": 4, "output_tokens": 4},
            },
        )

    settings = Settings(
        _env_file=None,
        openai_api_key="fixture",
        llm_default_model="fixture",
        llm_timeout_seconds=1,
        llm_max_input_bytes=10000,
        llm_max_output_tokens=512,
        llm_max_response_bytes=10000,
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await classify_saved_posting(
            session_factory, posting_id, settings=settings, http_client=client
        )
        await classify_saved_posting(
            session_factory, posting_id, settings=settings, http_client=client
        )
    async with session_factory() as db:
        stored = await db.scalar(select(JobPosting).where(JobPosting.id == posting_id))
        assert stored.domain_category == "finance"
        assert stored.raw_payload["main_tasks"] == ["Payments service"]
        assert stored.raw_payload["_domain_classification"]["evidence"] == "Payments service"
        assert stored.raw_payload["_domain_classification"]["status"] == "succeeded"
    assert len(calls) == 1


async def test_missing_domain_prompt_is_recorded_as_failure_without_failing_posting(
    session_factory,
):
    from app.features.analysis.posting_domain import classify_saved_posting

    async with session_factory.begin() as db:
        row = JobPosting(
            source="wanted",
            normalized_url="https://www.wanted.co.kr/wd/998",
            raw_url="https://www.wanted.co.kr/wd/998",
            parse_status="succeeded",
            raw_payload={"position": "Engineer"},
        )
        db.add(row)
        await db.flush()
        posting_id = row.id
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: (_ for _ in ()).throw(AssertionError("no model call"))
        )
    ) as client:
        await classify_saved_posting(
            session_factory, posting_id, settings=Settings(_env_file=None), http_client=client
        )
    async with session_factory() as db:
        stored = await db.get(JobPosting, posting_id)
        assert stored.parse_status == "succeeded"
        assert stored.domain_category == "etc"
        assert stored.raw_payload["_domain_classification"]["status"] == "failed"
