"""문서 Claim 대조의 실제 PostgreSQL 저장·재사용·소유권·원문 변경 경계."""

import asyncio
import hashlib
import json
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import select

from app.core.config import Settings
from app.db.models import (
    DocumentClaim,
    DocumentClaimComparison,
    Evidence,
    InterviewSession,
    LLMCallRecord,
    PromptVersion,
    SessionRepository,
    UserDocument,
)
from app.features.documents.claim_comparison import (
    load_claim_comparison_sources,
    prepare_selected_claim_comparisons,
)
from app.features.interview.prepare_lease import claim as acquire
from tests.features.interview.factories import make_interview, make_repo, make_run, make_user

SHA = "b" * 40


async def test_expired_same_job_comparison_can_be_reclaimed(app, monkeypatch):
    import pytest

    from app.features.documents import claim_comparison as module

    interview_id, job_id, claim_id, _, evidence_id = await seed(app)

    async def crash(*args, **kwargs):
        raise RuntimeError("simulated lost worker")

    original = module.compare_document_claims
    monkeypatch.setattr(module, "compare_document_claims", crash)
    with pytest.raises(RuntimeError, match="lost worker"):
        await prepare_selected_claim_comparisons(
            app.state.session_factory, interview_id, settings(), job_id=job_id
        )
    async with app.state.session_factory.begin() as db:
        row = await db.get(InterviewSession, interview_id)
        previous_run = row.context_state["document_claim_comparison_run_id"]
        row.context_state = {
            **row.context_state,
            "document_claim_comparison_expires_at": (
                datetime.now(UTC) - timedelta(seconds=1)
            ).isoformat(),
        }
    monkeypatch.setattr(module, "compare_document_claims", original)
    calls = []
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(provider(claim_id, evidence_id, calls))
    ) as http:
        await prepare_selected_claim_comparisons(
            app.state.session_factory, interview_id, settings(), http, job_id=job_id
        )
    assert len(calls) == 1
    async with app.state.session_factory() as db:
        row = await db.get(InterviewSession, interview_id)
        assert row.context_state["document_claim_comparison_status"] == "succeeded"
        assert row.context_state["document_claim_comparison_run_id"] != previous_run


async def seed(app, *, claim_type="implementation", with_code=True, prompt_version="claim_code_v1"):
    source = "API uses a cache"
    version = hashlib.sha256(source.encode()).hexdigest()
    async with app.state.session_factory.begin() as db:
        user = await make_user(db)
        run = await make_run(db, user)
        repo = await make_repo(db, run)
        document = UserDocument(
            user_id=user.id,
            doc_type="portfolio",
            filename="portfolio.txt",
            mime_type="text/plain",
            size_bytes=len(source),
            extracted_text=source,
            extracted_github_urls=[],
            extract_status="succeeded",
            is_truncated=False,
            source_snapshot={"text": source, "text_hash": version, "limitations": []},
            claims_status="succeeded",
            claims_source_version=version,
        )
        db.add(document)
        await db.flush()
        run.document_id = document.id
        interview = await make_interview(db, run, [repo], status="preparing")
        job_id = uuid4()
        acquire(interview, job_id)
        for row in await db.scalars(
            select(SessionRepository).where(SessionRepository.interview_session_id == interview.id)
        ):
            row.snapshot_head_sha = SHA
        item = DocumentClaim(
            document_id=document.id,
            claim_text=source,
            claim_type=claim_type,
            source_text=source,
            source_version=version,
            source_location={"start_line": 1, "end_line": 1},
        )
        db.add(item)
        await db.flush()
        document.claims_active_ids = [str(item.id)]
        code = None
        if with_code:
            code = Evidence(
                interview_session_id=interview.id,
                repository_id=repo.id,
                source_type="file",
                git_ref=SHA,
                path="app.py",
                snippet="cache.get(key)",
                start_line=1,
                end_line=1,
            )
            db.add(code)
        db.add(
            PromptVersion(
                task_name="claim_code",
                version=prompt_version,
                model="fixture",
                template="Compare only supplied sources",
                is_active=True,
            )
        )
        await db.flush()
        return interview.id, job_id, item.id, document.id, code.id if code else None


def settings():
    return Settings(
        _env_file=None,
        openai_api_key="fixture",
        llm_timeout_seconds=5,
        llm_max_output_tokens=1000,
        llm_max_input_bytes=65536,
        llm_max_response_bytes=65536,
    )


def provider(claim_id, evidence_id, calls):
    def respond(request):
        calls.append(request)
        content = {
            "comparisons": [
                {
                    "claim_id": str(claim_id),
                    "status": "consistent",
                    "reason": "Cache lookup is present.",
                    "evidence_quotes": [
                        {"evidence_id": str(evidence_id), "quote": "cache.get(key)"}
                    ],
                    "limitations": [],
                }
            ]
        }
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
                        "content": [{"type": "output_text", "text": json.dumps(content)}],
                    }
                ],
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
        )

    return respond


@pytest.mark.parametrize("version", ["claim_code_v1", "claim_code_v1@luna-local"])
async def test_comparison_is_saved_reused_and_has_independent_source_version(app, version):
    interview_id, job_id, claim_id, _, evidence_id = await seed(app, prompt_version=version)
    calls = []
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(provider(claim_id, evidence_id, calls))
    ) as http:
        for _ in range(2):
            await prepare_selected_claim_comparisons(
                app.state.session_factory, interview_id, settings(), http, job_id=job_id
            )
    assert len(calls) == 1
    async with app.state.session_factory() as db:
        row = await db.scalar(select(DocumentClaimComparison))
        assert row.status == "consistent" and row.execution_status == "succeeded"
        assert row.prompt_version == version
        record = await db.get(LLMCallRecord, row.run_id)
        assert record.attempts[0]["prompt_version"] == version
        assert row.code_sources[0]["git_ref"] == SHA
        assert row.code_sources[0]["path"] == "app.py"
        interview = await db.get(InterviewSession, interview_id)
        sources = await load_claim_comparison_sources(db, interview)
        assert len(sources) == 1 and sources[0].kind == "document_claim_comparison"
        assert len(sources[0].version) == 64
        assert sources[0].version != row.document_version
        assert "not_personal_contribution_evidence" in sources[0].limitations


async def test_no_code_stays_unverified_without_http(app):
    interview_id, job_id, _, _, _ = await seed(app, with_code=False)
    async with app.state.session_factory.begin() as db:
        await db.delete(
            await db.scalar(select(PromptVersion).where(PromptVersion.task_name == "claim_code"))
        )

    async def forbidden(request):
        raise AssertionError("No model call is needed without code")

    async with httpx.AsyncClient(transport=httpx.MockTransport(forbidden)) as http:
        await prepare_selected_claim_comparisons(
            app.state.session_factory, interview_id, settings(), http, job_id=job_id
        )
    async with app.state.session_factory() as db:
        row = await db.scalar(select(DocumentClaimComparison))
        assert row.status == "unverified" and row.execution_status == "succeeded"
        assert "code_evidence_unavailable" in row.result["limitations"]


async def test_lost_preparation_owner_cannot_run_or_store_comparison(app):
    interview_id, _, _, _, _ = await seed(app)
    await prepare_selected_claim_comparisons(
        app.state.session_factory, interview_id, settings(), job_id=uuid4()
    )
    async with app.state.session_factory() as db:
        assert await db.scalar(select(DocumentClaimComparison)) is None


async def test_changed_document_during_model_call_discards_old_result(app):
    interview_id, job_id, claim_id, document_id, evidence_id = await seed(app)
    respond = provider(claim_id, evidence_id, [])

    async def changed(request):
        async with app.state.session_factory.begin() as db:
            document = await db.get(UserDocument, document_id)
            text = "The document was replaced"
            document.source_snapshot = {
                "text": text,
                "text_hash": hashlib.sha256(text.encode()).hexdigest(),
            }
        return respond(request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(changed)) as http:
        await prepare_selected_claim_comparisons(
            app.state.session_factory, interview_id, settings(), http, job_id=job_id
        )
    async with app.state.session_factory() as db:
        assert await db.scalar(select(DocumentClaimComparison)) is None
        record = await db.scalar(
            select(LLMCallRecord).where(LLMCallRecord.task_name == "claim_code")
        )
        assert record.discard_reason == "comparison_input_or_preparation_changed"


async def test_changed_code_is_not_presented_as_valid_comparison(app):
    interview_id, job_id, claim_id, _, evidence_id = await seed(app)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(provider(claim_id, evidence_id, []))
    ) as http:
        await prepare_selected_claim_comparisons(
            app.state.session_factory, interview_id, settings(), http, job_id=job_id
        )
    async with app.state.session_factory.begin() as db:
        evidence = await db.get(Evidence, evidence_id)
        evidence.snippet = "Different code"
    async with app.state.session_factory() as db:
        sources = await load_claim_comparison_sources(
            db, await db.get(InterviewSession, interview_id)
        )
        assert "comparison_code_source_unavailable" in sources[0].limitations
        assert json.loads(sources[0].content)["comparison"]["status"] == "unverified"


async def test_explicit_new_preparation_keeps_failed_comparison_immutable(app):
    interview_id, job_id, claim_id, _, evidence_id = await seed(app)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(400))
    ) as http:
        await prepare_selected_claim_comparisons(
            app.state.session_factory, interview_id, settings(), http, job_id=job_id
        )
    async with app.state.session_factory.begin() as db:
        old = await db.scalar(select(DocumentClaimComparison))
        old_id, old_result = old.id, dict(old.result)
        assert old.execution_status == "failed"
        new_job = uuid4()
        acquire(await db.get(InterviewSession, interview_id), new_job)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(provider(claim_id, evidence_id, []))
    ) as http:
        await prepare_selected_claim_comparisons(
            app.state.session_factory, interview_id, settings(), http, job_id=new_job
        )
    async with app.state.session_factory() as db:
        old = await db.get(DocumentClaimComparison, old_id)
        assert old.result == old_result and old.execution_status == "failed"
        interview = await db.get(InterviewSession, interview_id)
        current = await load_claim_comparison_sources(db, interview)
        archive = await load_claim_comparison_sources(db, interview, include_historical=True)
        assert len(current) == 1 and current[0].source_id != str(old_id)
        assert len(archive) == 2


async def test_concurrent_same_preparation_reserves_only_one_model_batch(app):
    interview_id, job_id, claim_id, _, evidence_id = await seed(app)
    entered, release = asyncio.Event(), asyncio.Event()
    calls = []
    respond = provider(claim_id, evidence_id, calls)

    async def paused(request):
        entered.set()
        await release.wait()
        return respond(request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(paused)) as http:
        first = asyncio.create_task(
            prepare_selected_claim_comparisons(
                app.state.session_factory, interview_id, settings(), http, job_id=job_id
            )
        )
        try:
            await asyncio.wait_for(entered.wait(), 5)
            await prepare_selected_claim_comparisons(
                app.state.session_factory, interview_id, settings(), http, job_id=job_id
            )
        finally:
            release.set()
        await first
    assert len(calls) == 1


async def test_expired_batch_late_result_cannot_replace_reclaimed_batch(app):
    interview_id, job_id, claim_id, _, evidence_id = await seed(app)
    entered, release = asyncio.Event(), asyncio.Event()
    calls = []
    respond = provider(claim_id, evidence_id, calls)

    async def paused(request):
        entered.set()
        await release.wait()
        return respond(request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(paused)) as old_http:
        first = asyncio.create_task(
            prepare_selected_claim_comparisons(
                app.state.session_factory, interview_id, settings(), old_http, job_id=job_id
            )
        )
        await asyncio.wait_for(entered.wait(), 5)
        async with app.state.session_factory.begin() as db:
            row = await db.get(InterviewSession, interview_id)
            old_run = row.context_state["document_claim_comparison_run_id"]
            row.context_state = {
                **row.context_state,
                "document_claim_comparison_expires_at": (
                    datetime.now(UTC) - timedelta(seconds=1)
                ).isoformat(),
            }
        try:
            async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
                await prepare_selected_claim_comparisons(
                    app.state.session_factory, interview_id, settings(), http, job_id=job_id
                )
        finally:
            release.set()
            await asyncio.wait_for(first, 5)
    assert len(calls) == 2
    async with app.state.session_factory() as db:
        row = await db.get(InterviewSession, interview_id)
        old = await db.get(LLMCallRecord, UUID(old_run))
        assert old.discard_reason == "preparation_changed"
        assert row.context_state["document_claim_comparison_status"] == "succeeded"
        assert row.context_state["document_claim_comparison_run_id"] != old_run
        assert len(list(await db.scalars(select(DocumentClaimComparison)))) == 1
