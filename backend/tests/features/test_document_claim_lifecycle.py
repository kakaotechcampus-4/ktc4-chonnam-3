"""실제 DB에서 선택·버전·취소·작업 교체의 Claim 저장 경계를 검사한다."""

import asyncio
from uuid import uuid4

import pytest
from devon_ai.llm_tasks.doc_claims import ClaimExtraction
from devon_ai.llm_tasks.doc_claims import DocumentClaim as AIClaim
from sqlalchemy import select

from app.core.config import Settings
from app.db.models import (
    DocumentClaim,
    InterviewSession,
    LLMCallRecord,
    PromptVersion,
    UserDocument,
)
from app.features.documents import claims
from app.features.interview.prepare_lease import claim
from app.features.interview.supplemental_sources import load_supplemental_sources
from tests.features.interview.factories import make_interview, make_repo, make_run, make_user


@pytest.fixture
async def selected(app):
    import hashlib

    async with app.state.session_factory.begin() as db:
        user = await make_user(db)
        run = await make_run(db, user)
        repo = await make_repo(db, run)
        documents = []
        for kind in ("portfolio", "cover_letter", "cover_letter"):
            text = f"Selected {kind} {len(documents)}"
            document = UserDocument(
                user_id=user.id,
                doc_type=kind,
                filename=kind + ".txt",
                mime_type="text/plain",
                size_bytes=len(text),
                extracted_text=text,
                extract_status="succeeded",
                source_snapshot={
                    "text": text,
                    "text_hash": hashlib.sha256(text.encode()).hexdigest(),
                    "source_hash": None,
                    "blocks": [],
                    "limitations": [],
                },
            )
            db.add(document)
            await db.flush()
            documents.append(document)
        run.document_id, run.cover_letter_document_id = documents[0].id, documents[1].id
        interview = await make_interview(db, run, [repo], status="preparing")
        job_id = uuid4()
        claim(interview, job_id)
        db.add(
            PromptVersion(
                task_name="doc_claims",
                version="doc_claims_v1",
                model="test",
                template="claims",
                is_active=True,
            )
        )
    return interview.id, job_id, [item.id for item in documents]


def settings():
    return Settings(
        _env_file=None,
        openai_api_key="test",
        llm_timeout_seconds=2,
        llm_max_output_tokens=1000,
        llm_max_input_bytes=10000,
        llm_max_response_bytes=10000,
    )


async def extract(text, **kwargs):
    return ClaimExtraction((AIClaim(text, "role", (), 0, text),), None, ())


async def test_both_explicit_documents_reach_context_but_latest_unselected_does_not(
    app, selected, monkeypatch
):
    interview_id, job_id, ids = selected
    monkeypatch.setattr(claims, "analyze_document_claims", extract)
    await claims.prepare_selected_document_claims(
        app.state.session_factory, interview_id, settings(), job_id=job_id
    )
    async with app.state.session_factory() as db:
        rows = list(await db.scalars(select(DocumentClaim)))
        assert {item.document_id for item in rows} == set(ids[:2])
        sources = await load_supplemental_sources(db, interview_id)
        assert len(sources) == 2
        assert all(str(ids[2]) not in item.location for item in sources)


async def test_new_prompt_reextracts_and_retires_old_claims_from_current_context(
    app, selected, monkeypatch
):
    interview_id, job_id, ids = selected
    monkeypatch.setattr(claims, "analyze_document_claims", extract)
    await claims.prepare_selected_document_claims(
        app.state.session_factory, interview_id, settings(), job_id=job_id
    )
    async with app.state.session_factory.begin() as db:
        old = await db.scalar(select(PromptVersion))
        old.is_active = False
        await db.flush()
        db.add(
            PromptVersion(
                task_name="doc_claims",
                version="doc_claims_v2",
                model="test",
                template="new",
                is_active=True,
            )
        )
    calls = []

    async def empty(text, **kwargs):
        calls.append(text)
        return ClaimExtraction((), None, ())

    monkeypatch.setattr(claims, "analyze_document_claims", empty)
    await claims.prepare_selected_document_claims(
        app.state.session_factory, interview_id, settings(), job_id=job_id
    )
    assert len(calls) == 2
    async with app.state.session_factory() as db:
        assert await load_supplemental_sources(db, interview_id) == ()
        assert len(await load_supplemental_sources(db, interview_id, max_total_bytes=None)) == 2
        assert (await db.get(UserDocument, ids[0])).claims_prompt_version == "doc_claims_v2"


async def test_old_job_cannot_replace_new_preparation_or_heartbeat_state(
    app, selected, monkeypatch
):
    interview_id, job_id, ids = selected
    new_job = uuid4()

    async def takeover(text, **kwargs):
        async with app.state.session_factory.begin() as db:
            row = await db.get(InterviewSession, interview_id)
            claim(row, new_job)
            row.context_state = {**row.context_state, "heartbeat_marker": "new"}
        return await extract(text)

    monkeypatch.setattr(claims, "analyze_document_claims", takeover)
    await claims.prepare_selected_document_claims(
        app.state.session_factory, interview_id, settings(), job_id=job_id
    )
    async with app.state.session_factory() as db:
        assert await db.scalar(select(DocumentClaim)) is None
        row = await db.get(InterviewSession, interview_id)
        assert row.context_state["prepare_job_id"] == str(new_job)
        assert row.context_state["heartbeat_marker"] == "new"
        record = await db.scalar(select(LLMCallRecord))
        assert record.discard_reason == "selected_document_or_preparation_changed"


async def test_cancelled_call_cleans_only_its_reservation_and_records_failure(
    app, selected, monkeypatch
):
    interview_id, job_id, ids = selected
    entered = asyncio.Event()

    async def wait(text, **kwargs):
        entered.set()
        await asyncio.Future()

    monkeypatch.setattr(claims, "analyze_document_claims", wait)
    task = asyncio.create_task(
        claims.prepare_selected_document_claims(
            app.state.session_factory, interview_id, settings(), job_id=job_id
        )
    )
    await asyncio.wait_for(entered.wait(), 5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    async with app.state.session_factory() as db:
        document = await db.get(UserDocument, ids[0])
        assert document.claims_status == "pending" and document.claims_run_id is None
        record = await db.scalar(select(LLMCallRecord))
        assert record.discard_reason == "preparation_cancelled"
        assert record.failure["error_code"] == "document_claims_cancelled"


async def test_document_lock_refreshes_a_reservation_changed_after_selection(
    app, selected, monkeypatch
):
    from sqlalchemy import update

    interview_id, job_id, ids = selected
    other_job = uuid4()
    original = claims.selected_documents
    selections = 0
    observed = []

    async def select_then_reserve(db, row):
        nonlocal selections
        documents = await original(db, row)
        selections += 1
        if selections == 2:
            # 첫 조회와 잠금 사이에 다른 면접이 같은 문서의 분석을 예약한다.
            async with app.state.session_factory.begin() as other:
                await other.execute(
                    update(UserDocument)
                    .where(UserDocument.id == ids[0])
                    .values(claims_status="running", claims_run_id=other_job)
                )
        return documents

    async def collect(text, **kwargs):
        observed.append(text)
        return await extract(text, **kwargs)

    monkeypatch.setattr(claims, "selected_documents", select_then_reserve)
    monkeypatch.setattr(claims, "analyze_document_claims", collect)
    await claims.prepare_selected_document_claims(
        app.state.session_factory, interview_id, settings(), job_id=job_id
    )
    assert len(observed) == 1 and "cover_letter" in observed[0]
    async with app.state.session_factory() as db:
        assert (await db.get(UserDocument, ids[0])).claims_run_id == other_job
