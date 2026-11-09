"""선택 문서만 분석하고 검증한 원문 위치를 영속화하는 통합 검사."""

from uuid import uuid4

import httpx
from sqlalchemy import select

from app.core.config import Settings
from app.db.models import DocumentClaim, PromptVersion, UserDocument
from app.features.documents.source_snapshot import snapshot_document
from app.integrations.extract.base import ExtractionResult
from app.shared.enums import DocumentExtractStatus
from tests.features.interview.factories import make_interview, make_repo, make_run, make_user


async def test_selected_claim_is_saved_with_exact_line_and_reused(app):
    from app.features.documents.claims import prepare_selected_document_claims

    source = "프로젝트\n\n  제가 구현한 API  \n"
    async with app.state.session_factory.begin() as db:
        user = await make_user(db)
        run = await make_run(db, user)
        repo = await make_repo(db, run)
        document = UserDocument(
            user_id=user.id,
            doc_type="portfolio",
            filename="portfolio.txt",
            mime_type="text/plain",
            size_bytes=len(source.encode()),
            extracted_text=source,
            extracted_github_urls=[],
            extract_status="succeeded",
            is_truncated=False,
            source_snapshot=snapshot_document(
                source.encode(),
                ExtractionResult(source, DocumentExtractStatus.SUCCEEDED),
                max_chars=10000,
            ),
        )
        db.add(document)
        await db.flush()
        run.document_id = document.id
        interview = await make_interview(db, run, [repo], status="preparing")
        from app.features.interview.prepare_lease import claim

        job_id = uuid4()
        claim(interview, job_id)
        db.add(
            PromptVersion(
                task_name="doc_claims",
                version="doc_claims_v1",
                model="test-model",
                template="Extract only sourced claims",
                is_active=True,
            )
        )
    calls = []

    def provider(request):
        import json

        calls.append(request)
        content = {
            "claims": [
                {
                    "claim_text": "API를 구현했다",
                    "claim_type": "implementation",
                    "tech_tags": [],
                    "line_id": "L1",
                }
            ]
        }
        return httpx.Response(
            200,
            json={
                "id": "test",
                "model": "test-model",
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "status": "completed",
                        "content": [{"type": "output_text", "text": json.dumps(content)}],
                    }
                ],
                "usage": {"input_tokens": 10, "output_tokens": 10},
            },
        )

    settings = Settings(
        _env_file=None,
        openai_api_key="test",
        llm_timeout_seconds=5,
        llm_max_output_tokens=1000,
        llm_max_input_bytes=20000,
        llm_max_response_bytes=20000,
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as http:
        await prepare_selected_document_claims(
            app.state.session_factory, interview.id, settings, http, job_id=job_id
        )
        await prepare_selected_document_claims(
            app.state.session_factory, interview.id, settings, http, job_id=job_id
        )
    assert len(calls) == 1
    async with app.state.session_factory() as db:
        claim = await db.scalar(
            select(DocumentClaim).where(DocumentClaim.document_id == document.id)
        )
        assert claim.source_text == "  제가 구현한 API  "
        assert claim.source_location["start_line"] == 3
        stored = await db.get(UserDocument, document.id)
        assert stored.claims_status == "succeeded"
