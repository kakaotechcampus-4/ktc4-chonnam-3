"""실제 DB에서 선택·버전·취소·작업 교체의 Claim 저장 경계를 검사한다."""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
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
        assert document.claims_lease_expires_at is None
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


async def test_invalid_claim_locations_finish_failed_without_partial_rows(
    app, selected, monkeypatch
):
    interview_id, job_id, ids = selected

    async def invalid(text, **kwargs):
        return ClaimExtraction(
            (AIClaim("valid", "role", (), 0, text), AIClaim("invalid", "role", (), 9, "missing")),
            None,
            (),
        )

    monkeypatch.setattr(claims, "analyze_document_claims", invalid)
    await claims.prepare_selected_document_claims(
        app.state.session_factory, interview_id, settings(), job_id=job_id
    )
    async with app.state.session_factory() as db:
        assert await db.scalar(select(DocumentClaim)) is None
        for document_id in ids[:2]:
            document = await db.get(UserDocument, document_id)
            assert document.claims_status == "failed"
            assert document.claims_error_code == "document_source_invalid"
            assert document.claims_run_id is None
        records = list(await db.scalars(select(LLMCallRecord)))
        assert len(records) == 2
        assert all(row.failure["error_code"] == "document_source_invalid" for row in records)


async def test_deployment_identity_survives_database_loader_and_model_bridge(app, selected):
    interview_id, job_id, ids = selected
    version = "doc_claims_v1@luna-local"
    async with app.state.session_factory.begin() as db:
        (await db.scalar(select(PromptVersion))).is_active = False
        await db.flush()
        db.add(
            PromptVersion(
                task_name="doc_claims",
                version=version,
                model="test",
                template="claims",
                is_active=True,
            )
        )
    calls = []

    def respond(request):
        calls.append(request)
        body = json.loads(request.content)
        assert body["model"] == "test"
        return httpx.Response(
            200,
            json={
                "id": "fixture",
                "model": "test",
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
                                    {
                                        "claims": [
                                            {
                                                "claim_text": "Role stated",
                                                "claim_type": "role",
                                                "tech_tags": [],
                                                "line_id": "L0",
                                            }
                                        ]
                                    }
                                ),
                            }
                        ],
                    }
                ],
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        for _ in range(2):
            await claims.prepare_selected_document_claims(
                app.state.session_factory, interview_id, settings(), http, job_id=job_id
            )
    assert len(calls) == 2
    async with app.state.session_factory() as db:
        for item in ids[:2]:
            assert (await db.get(UserDocument, item)).claims_prompt_version == version
        records = list(await db.scalars(select(LLMCallRecord)))
        assert len(records) == 2
        assert all(row.attempts[0]["prompt_version"] == version for row in records)


async def test_other_interview_waits_for_shared_claims_and_synchronizes_status(
    app, selected, monkeypatch
):
    from app.db.models import AnalysisJob, User

    interview_id, job_id, _ = selected
    async with app.state.session_factory.begin() as db:
        original = await db.get(InterviewSession, interview_id)
        previous_run = await db.get(AnalysisJob, original.analysis_job_id)
        user = await db.get(User, original.user_id)
        run = await make_run(db, user)
        run.document_id = previous_run.document_id
        run.cover_letter_document_id = previous_run.cover_letter_document_id
        repo = await make_repo(db, run)
        second = await make_interview(db, run, [repo], status="preparing")
        second_job = uuid4()
        claim(second, second_job)
    entered, release = asyncio.Event(), asyncio.Event()
    calls = []

    async def blocked(text, **kwargs):
        calls.append(text)
        if "portfolio" in text:
            entered.set()
            await release.wait()
        return await extract(text)

    monkeypatch.setattr(claims, "analyze_document_claims", blocked)
    first = asyncio.create_task(
        claims.prepare_selected_document_claims(
            app.state.session_factory, interview_id, settings(), job_id=job_id
        )
    )
    await asyncio.wait_for(entered.wait(), 5)
    other = asyncio.create_task(
        claims.prepare_selected_document_claims(
            app.state.session_factory, second.id, settings(), job_id=second_job
        )
    )
    await asyncio.sleep(0.05)
    release.set()
    await asyncio.wait_for(asyncio.gather(first, other), 10)
    assert len(calls) == 2
    async with app.state.session_factory() as db:
        row = await db.get(InterviewSession, second.id)
        assert row.context_state["document_claims_status"] == "succeeded"
        assert all(
            item["status"] == "succeeded"
            for item in row.context_state["document_claims_results"].values()
        )


async def test_other_running_document_finishes_with_explicit_unavailability(
    app, selected, monkeypatch
):
    interview_id, job_id, ids = selected
    other_run = uuid4()
    fixed_now = datetime(2026, 11, 10, tzinfo=UTC)

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed_now

    monkeypatch.setattr(claims, "datetime", FixedDateTime)
    async with app.state.session_factory.begin() as db:
        first = await db.get(UserDocument, ids[0])
        first.claims_status, first.claims_run_id = "running", other_run
        first.updated_at = fixed_now - timedelta(days=1)
        first.claims_lease_expires_at = fixed_now + timedelta(hours=1)
        second = await db.get(UserDocument, ids[1])
        second.claims_status = "succeeded"
        second.claims_source_version = second.source_snapshot["text_hash"]
        second.claims_prompt_version = "doc_claims_v1"

    async def unexpected(*args, **kwargs):
        raise AssertionError("A shared live reservation must not start another model call")

    monkeypatch.setattr(claims, "analyze_document_claims", unexpected)
    bounded = settings().model_copy(update={"llm_timeout_seconds": 0.05})
    await asyncio.wait_for(
        claims.prepare_selected_document_claims(
            app.state.session_factory, interview_id, bounded, job_id=job_id
        ),
        5,
    )
    async with app.state.session_factory() as db:
        document = await db.get(UserDocument, ids[0])
        row = await db.get(InterviewSession, interview_id)
        assert document.claims_status == "running" and document.claims_run_id == other_run
        assert row.context_state["document_claims_status"] == "not_available"
        assert row.context_state["document_claims_error_code"] == "document_claims_wait_timeout"
        assert await db.scalar(select(LLMCallRecord)) is None


@pytest.mark.parametrize("explicit_lease", [True, False])
async def test_short_waiter_cannot_steal_an_active_or_legacy_unknown_writer_lease(
    app, selected, monkeypatch, explicit_lease
):
    interview_id, job_id, ids = selected
    writer = uuid4()
    async with app.state.session_factory.begin() as db:
        row = await db.get(UserDocument, ids[0])
        row.claims_status, row.claims_run_id = "running", writer
        row.updated_at = datetime.now(UTC) - timedelta(hours=1)
        row.claims_lease_expires_at = (
            datetime.now(UTC) + timedelta(hours=1) if explicit_lease else None
        )

    async def forbidden(*args, **kwargs):
        raise AssertionError("A short waiter must not replace another writer")

    monkeypatch.setattr(claims, "analyze_document_claims", forbidden)
    bounded = settings().model_copy(update={"llm_timeout_seconds": 0.05})
    assert (
        await claims._prepare_document_once(
            app.state.session_factory, interview_id, ids[0], job_id, bounded, None
        )
        is True
    )
    async with app.state.session_factory() as db:
        row = await db.get(UserDocument, ids[0])
        assert row.claims_status == "running" and row.claims_run_id == writer


async def test_same_job_stale_document_result_cannot_replace_new_reservation(
    app, selected, monkeypatch
):
    interview_id, job_id, ids = selected
    entered, release = asyncio.Event(), asyncio.Event()
    requests = []

    async def delayed(text, **kwargs):
        requests.append(text)
        if len(requests) == 1:
            entered.set()
            await release.wait()
            label = "old"
        else:
            label = "new"
        return ClaimExtraction((AIClaim(label, "role", (), 0, text),), None, ())

    monkeypatch.setattr(claims, "analyze_document_claims", delayed)
    first = asyncio.create_task(
        claims.prepare_selected_document_claims(
            app.state.session_factory, interview_id, settings(), job_id=job_id
        )
    )
    await asyncio.wait_for(entered.wait(), 5)
    async with app.state.session_factory.begin() as db:
        document = await db.get(UserDocument, ids[0])
        old_run = document.claims_run_id
        document.claims_lease_expires_at = datetime.now(UTC) - timedelta(hours=1)
    try:
        await claims.prepare_selected_document_claims(
            app.state.session_factory, interview_id, settings(), job_id=job_id
        )
    finally:
        release.set()
        await asyncio.wait_for(first, 5)
    async with app.state.session_factory() as db:
        document = await db.get(UserDocument, ids[0])
        rows = list(
            await db.scalars(select(DocumentClaim).where(DocumentClaim.document_id == ids[0]))
        )
        assert len(rows) == 1 and rows[0].claim_text == "new"
        assert document.claims_active_ids == [str(rows[0].id)]
        assert (
            await db.get(LLMCallRecord, old_run)
        ).discard_reason == "selected_document_or_preparation_changed"
        assert (await db.get(InterviewSession, interview_id)).context_state[
            "document_claims_status"
        ] == "succeeded"
